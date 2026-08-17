# Field test brief — twincat-scope

**Read this cold. It assumes you know nothing about the repo or its history.**

You are being asked to test a change on a machine that has data nobody else has. Everything
below can be verified from this repository except the one thing that matters most, which is
why you are being asked.

---

## 1. What this is

`twincat-scope` is an agent skill for recording and diagnosing **TwinCAT 3 Scope**
measurements. Its central problem is that a scope file is far too large to read: ten minutes
of twenty channels at 1 kHz is twelve million samples. So the skill never hands back samples.
It hands back summaries, events and pictures, and only returns real rows once a time range is
known. That sequence is called **the ladder**:

| Rung | Verb | Question |
|---|---|---|
| 1 | `manifest` | What is in this file? |
| 2 | `stats` | Which channel is misbehaving? |
| 3 | `events` | When did it happen? |
| 4 | `plot` | What is the shape around then? |
| 5 | `correlate` | Which channel moved first? |
| 6 | `window` | What were the actual numbers? |

Everything is one script, `scripts/tcscope.py`, which emits JSON on stdout.

The one structural fact you need: **a Scope CSV is not `time,ch1,ch2,…`**. It is a horizontal
concatenation of independent acquisition groups, each with its own time column and often its
own sample rate:

```
<t0> <a0> <a1> | <t1> <b0> <b1> <b2> | <t2> <c0>
^ group 0      ^ group 1             ^ group 2
```

A physical row is therefore **not one instant in time**. Every channel is timestamped from its
own group's clock. Slow groups are usually "repeat-padded" — the same sample printed again on
the next row so all groups end together — and sometimes they are not, in which case the file
cannot support any cross-group timing claim at all.

## 2. Why you are being asked

A previous field review of this skill (kept in `evals/field-review-af54888.md`) was run on a
commissioning workstation against 19 genuine Scope exports and 7 real `.tcscopex` projects. It
confirmed the group model was correct and found four defects. All four have now been fixed.

**The fixes were verified only against synthetic structural fixtures.** Those fixtures copy the
*shape* of the real exports — group boundaries, delimiters, decimal separators, metadata keys,
time-column behaviour — but they are 200 to 1500 rows of invented signal. The real recordings
carry customer machine behaviour and are not in this repo and never will be.

So: this repo can prove the change is self-consistent. It cannot prove the reader still reads
real files correctly. Only a machine holding those 19 exports can.

## 3. Setting up

```bash
git clone git@github.com:SionVerhoef/twincat-scope.git
cd twincat-scope
uv run tests/test_verbs.py          # expect: 111/111 checks passed
```

`uv` handles dependencies from the script header; nothing else needs installing. If `uv` is
absent, install it (`winget install --id=astral-sh.uv -e`) or invoke `scripts/tcscope.py` with
a Python 3.10+ that has numpy, pyarrow and matplotlib. Test fixtures are generated on demand —
`tests/test_verbs.py` regenerates them before it runs, so a fresh clone needs no extra step.

Verbs are invoked as:

```bash
uv run scripts/tcscope.py manifest <file.csv>
uv run scripts/tcscope.py events <file.csv> --channels <name>
uv run scripts/tcscope.py window <file.csv> --start 12.0 --end 12.2
python3 scripts/tcscope.py doctor          # works with nothing installed
```

## 4. THE critical check

**The CSV parser changed.** It now reads in 20 000-row chunks and lets numpy convert the
strings, instead of building a Python list of lists of floats for the whole file. This halved
peak memory and made it 30% faster — but it touches the exact code path the previous review
validated against all 19 files.

Sniffing, delimiter election, decimal detection, group parsing and line indexing were
deliberately **not** touched. `manifest` output was checked byte-identical between the old and
new reader on all 8 repo fixtures. That is the strongest check available without the real
files. It is not proof.

> **So the first thing to do: re-run `manifest` on all 19 exports and confirm every row of the
> ground-truth table in `evals/field-review-af54888.md` §"Ground truth" still matches exactly —
> ncols, group count, channel count, row count, and `max_skew_ms`.**

If any row differs, stop and report it before looking at anything else. A silent column
misalignment is the worst failure this tool can have, and it is the one this change could
plausibly cause.

## 5. What changed, and what to check

### 5.1 `events` — rewritten (this was the critical defect)

The old detector was unusable on real motion data: it fired 170–413 events per channel, and
because it truncated **chronologically**, the default 100 events came back from the first
10 ms of a 10.8 s recording while the actual fault sat at 9 s.

Two root causes, both fixed:

- **The threshold degenerated.** An axis at rest has over half its first differences sitting at
  the encoder's quantisation floor, so the median absolute deviation collapsed to ~1e-9 — which
  is non-zero, so it passed the old zero-guard — and `6·MAD·1.4826` became a threshold every
  acceleration sample cleared. There is now a floor: `--min-step` (default 0.01) keeps the
  threshold at no less than 1% of the channel's own travel.
- **A sustained change was reported once per sample.** Consecutive over-threshold differences
  are now coalesced into a single excursion. Same-direction excursions within `--spike-width`
  samples are joined too, because a ramp sitting near the threshold flickers across it and
  otherwise fragments into dozens of pieces.

**New and changed event kinds:**

| Kind | Meaning |
|---|---|
| `step` | A discontinuity that stayed — setpoint jump, mode switch, encoder jump |
| `ramp` | **New.** A commanded move: it travelled, but took many samples. Excursions wider than `--ramp-samples` (default 3) |
| `spike` | Transient — leaves and returns within `--spike-width` |
| `transition` | **New.** A two-valued (digital) channel changed state |
| `flatline` | Signal stopped updating for a sustained run |
| `clipping` | Signal pinned at a rail |
| `crossing` | A `--threshold` you supplied was crossed |

Two-valued channels now emit `transition` and are **exempt** from the clipping and flatline
tests, which describe a BOOL wrongly in both directions (a BOOL sits at both its rails 100% of
the time and holds each state as long as the machine needs it).

**New output fields.** `events` now returns:

```
count            every event found
events[]         what fits under --max-events; each has a `severity`
truncated        whether count > max-events
severity         (string) explains the severity scale
ranking          (string) explains the ordering
summary.by_kind          every event by kind, INCLUDING ones not returned
summary.by_channel       every event by channel, same
summary.per_channel_max  the worst channel's total
summary.returned         how many were returned
summary.time_histogram   {t_first, t_last, bins[10], timed}
```

`severity` is a multiple of each detector's own threshold. `ramp`, `transition` and `crossing`
are descriptive rather than anomalous and are always 1.0. `time_histogram.timed` is below
`count` by however many `clipping` events there are, because clipping describes a channel
rather than an instant and has no timestamp.

**Truncation is now ranked, not chronological:** the worst event in each tenth of the
recording, worst tenth first. So a truncated answer spans the recording and still contains the
single worst thing in it.

**What to check:**

- Event counts per channel on the real exports. The measured before-numbers were 170, 99, 340
  and 413 per channel on four named files (see the field review, exports D, A, F and J). Report
  the after-numbers for the same files.
- That genuine faults you know about are still found, and rank near the top by `severity`.
- That commanded axis moves come back as `ramp`, not as a pile of `step`s.
- That `summary` totals are consistent with `count`.
- Whether `--min-step` at 1% is too aggressive for any real signal — specifically, whether any
  fault you know about has gone missing. This is the change most likely to cause a false
  negative. If something is missed, try `--sigma 3 --min-step 0.001` and report the difference.

### 5.2 `window` — was double-counting

It indexed raw file rows rather than distinct time instants, so on a repeat-padded group it
printed every sample twice under one timestamp, and its `--max-rows` cap was evaluated against
padding — biting at half the promised width. It now reads distinct instants like every other
verb.

Check on a padded group: no two consecutive rows share a timestamp, and row count matches the
group's `n_samples` over the same span.

### 5.3 `stats` — one new field

`n_samples` per channel, so a standard deviation can be audited against how many points it was
computed over. `stats` was already de-duplicating correctly; this only makes it visible.

### 5.4 `checkscope` — acquisition load is now graded

The old warning threshold (100 000 samples/s, later 20 000) sat above every real project anyone
had built — the densest of the 7 measured projects is 16 250 — so it never fired and graded
nothing. It is now bands, taken from that measured distribution:

| Band | samples/s |
|---|---|
| `typical` | ≤ 6 000 |
| `moderate` | ≤ 10 000 |
| `high` | ≤ 20 000 — draws a note |
| warn | > 20 000 |

Output gains `load_band` and `load_bands_samples_per_second`. Re-run `checkscope` on the 7 real
projects and confirm the bands land sensibly — the expectation is the two densest fall in
`high` and the rest below.

### 5.5 Scale — now measured

`tests/make_scale_fixture.py` generates a large export (never committed);
`tests/bench_scale.py` reports wall clock and peak RSS per verb. Measured on a small Linux
container, 20 channels in two groups:

| Samples | File | Per verb | Peak RSS |
|---|---|---|---|
| 0.4 M | 5.7 MB | ~1 s | 66 MB |
| 2 M | 28.6 MB | ~4 s | 186 MB |
| 10 M | 143.6 MB | 15–16 s | 340 MB |
| 20 M | 288.3 MB | 31–42 s | 630 MB |

Peak memory tracks the **file size**, not the sample count: roughly 25 MB + 2.2 × file size.
Also measured: one 13.6 s `ingest` turns that 143.6 MB CSV into 11 MB of Parquet, after which
the same verbs run in 1.8–3.3 s instead of 15–16 s.

Worth confirming on real hardware, since these numbers came from a constrained container:

```bash
python3 tests/make_scale_fixture.py --rows 500000 -o scale.csv
python3 tests/bench_scale.py scale.csv
```

## 6. Acceptance criteria

These came from the previous review. Eight are met in-repo; **one can only be checked by you**,
and one was implemented differently — read that one carefully.

| # | Criterion | State |
|---|---|---|
| 1 | On a mostly-at-rest REAL64 fixture, `events` returns < 5 events/channel by default and the planted step is among them | Met — 4 max, planted fault ranked first |
| 2 | Severity-ranked or time-stratified; truncated set spans > 80% of duration | **Implemented differently — see below** |
| 3 | `events` always returns per-channel and per-kind totals, even when truncated | Met |
| 4 | `window` on a `repeat_factor > 1` group emits no duplicate timestamps; row count equals `n_samples` | Met |
| 5 | The `window` row cap is evaluated on de-duplicated samples | Met |
| 6 | `stats` exposes a per-channel sample count | Met |
| 7 | A ≥ 10 M-sample fixture exists; verbs complete within a documented time and memory budget | Met |
| 8 | The load warning fires on a realistic project, or is removed | Met — replaced with bands |
| 9 | **All 19 ground-truth rows remain exact** | **Only you can check this** |

**On criterion 2.** "Spans > 80% of the recording's duration" is not achievable in general: no
ranking can return an event from a stretch where none happened, and a recording that is quiet
at both ends will never satisfy it. It is implemented as *worst event in each tenth of the
recording, worst tenth first*, and tested against 80% of the span **the events themselves
occupy**. On your real files, where events are spread throughout, the original wording should
hold in practice — please check whether it does, since that is the case the criterion was
written for.

## 7. Known limitations — already understood, not bugs to re-report

- **`clipping` fires on an axis parked at the end of its travel.** A rest position and a rail
  are identical in the data. Requiring the signal to leave the rail and return was tried and
  defeated by LSB dither — a parked channel produced 427 separate runs at its rail. Left as a
  documented limitation rather than shipping an unvalidated heuristic. **If you can suggest a
  discriminator that survives the real files, that is the single most useful thing you could
  add.** A candidate is the speed at which the signal enters and leaves the rail.
- **Peak RSS is still ~2.2 × file size**, because the decoded text and its line list are alive
  at once. Streaming needs an exact byte offset out of `sniff_csv` first, and `str.splitlines()`
  breaks on a wider separator set than a byte-level split — a naive stream desyncs columns
  silently, which is precisely the failure class this tool exists to avoid.

## 8. Verified correct — do NOT "fix" these

Both were checked against the raw bytes of the source files and are now regression-tested.

- **Symbol names truncated mid-parenthesis.** Beckhoff's own exporter writes them that way, and
  every symbol under the affected axis is truncated identically. The reader is being faithful.
  Do not add parenthesis-balancing.
- **`unit: "(None)"`.** The literal string TwinCAT writes in the Unit metadata row. Do not
  coerce it to `null`. Round-tripping what the source says beats guessing what it meant.

## 9. Not yet tested by anyone

State this in your report if you do not get to it — the skill's own rules require saying what
was not checked rather than implying coverage.

- `plot` has never been exercised on a real file. Label readability with full symbol paths at
  fontsize 8 is an open question.
- `ingest` to Parquet against a real large export (only the generated fixture was used).
- `newscope` end to end.
- `doctor` on a machine without `TC3ScopeExportTool.exe`.
- Whether any generated `.tcscopex` opens in TwinCAT. **Nothing in this repo has ever been
  opened in real TwinCAT**, and the skill says so rather than implying otherwise.

## 10. Rules for your report — please read, this one bit us

**This repository is public, and it was recently scrubbed of customer machine data.** It had
been carrying a real AMS net ID as the copy-paste example in `SKILL.md` and three other files,
along with real NC symbol paths, hardware tags, TwinCAT project names and PLC variable names.
All of it has been anonymised, in the working tree and in every commit of the published
history, and a test now enforces that no tracked file contains an AMS net ID outside four
allowed placeholders.

So, when reporting:

- **Never paste real machine identifiers.** No net IDs, symbol paths, hardware/terminal tags,
  project names, export file names, PLC variable names, site or customer names.
- **Use the existing substitution convention.** Exports are lettered `A`–`K` and projects
  `A`–`G` in `evals/field-review-af54888.md`; reuse those labels so the two documents line up.
- **Numbers are never the problem — report them exactly.** Column counts, group layouts, row
  counts, skews, sample rates, event counts, timings. The numbers are the evidence; the names
  never were.
- Describe channels by role rather than name: "a velocity channel", "the position channel on
  the slow group".

Report as a file in the repo (`evals/field-review-<sha>.md`, following the existing one's
shape) or as a message — either is fine, but keep it anonymised in both.

## 11. Safety rules this skill operates under

These are not negotiable and apply to you while testing:

1. **Never author safety logic** — no TwinSAFE, no FSoE, no safety-PLC configuration.
2. **Never write to or activate a live machine.** Reading measurements is safe. Writing a
   variable, activating a configuration, or switching Run/Config mode is a human gesture —
   propose the command, do not run it.
3. **Never claim something is verified that you have not verified.** Say what you did not check.
4. **Recorded data never goes into git.** It is large, it does not diff, and it carries real
   machine behaviour.
