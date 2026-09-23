# Field test brief — twincat-scope

**Read this cold. It assumes you know nothing about the repo or its history.**

You are being asked to test a change on a machine that has data nobody else has. Everything
below can be verified from this repository except the one thing that matters most, which is
why you are being asked.

**Two parts.** **Part A (§4)** needs a machine running TwinCAT and is the priority. **Part B
(§5–§9)** needs the 19 real exports from the earlier review; do it only if they are on the
machine you are at. If there is time for one thing only, it is §4.1.

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
real files correctly. Only a machine holding those 19 exports can. That is Part B.

A second session (`evals/field-review-1fa0e9b.md`) then took the other half of the skill — the
one that *builds* recordings — to a running machine. A generated project opened cleanly in
Scope View, `checkscope` passed it, and it **recorded nothing**: wrong ADS port for the axis
channels, IEC type names where Scope wants its own, a fixed 8-byte width, and every channel
still named `Signal`. All four are fixed. A third session
(`evals/field-review-1fa0e9b-rounds.md`) confirmed the type, name and port fixes: patches to
the old version **recorded five NC axis channels**. A fourth
(`evals/field-review-fe9b487.md`) ran Part A on this skill's own output: items 1, 2 and 4
passed — NC axis and PLC bit, integer and real channels all recorded, `AxisStyle` accepted —
and 4.2, 4.5 and 4.7 were answered. A fifth (`evals/field-review-3e4c44d.md`) closed 4.4,
4.5, 4.6 and 4.8 and the omission test in 4.3, and a sixth (`evals/field-review-6872161.md`)
answered `ColorMode` — no theme-following option exists. A seventh
(`evals/field-review-44d4951.md`) recorded parked and still axes for 4.9. **Still open from
Part A:** running the new `checkscope --tmc` against a real `.tmc` (4.7), whether Claude Code
picks the skill up (4.10), and in 4.9 an axis parked exactly at a limit and a genuine
saturation — and all of Part B.

## 3. Setting up

```bash
git clone https://github.com/SionVerhoef/twincat-scope.git
cd twincat-scope
uv run tests/test_verbs.py          # expect every check to pass (158 at the time of writing)
```

**On Windows, write `py -3` wherever this brief says `python3`.** There `python3` usually hits
the Microsoft Store alias ("Python was not found") even with a working Python installed.

`uv` handles dependencies from the script header; nothing else needs installing. If `uv` is
absent, install it (`winget install --id=astral-sh.uv -e`) or invoke `scripts/tcscope.py` with
a Python 3.10+ that has numpy, pyarrow and matplotlib. Test fixtures are generated on demand —
`tests/test_verbs.py` regenerates them before it runs, so a fresh clone needs no extra step.

Verbs are invoked as:

```bash
uv run scripts/tcscope.py manifest <file.csv>
uv run scripts/tcscope.py events <file.csv> --channels <name>
uv run scripts/tcscope.py window <file.csv> --start 12.0 --end 12.2
py -3 scripts/tcscope.py doctor            # works with nothing installed
```

# Part A — on the machine, with TwinCAT

## 4. What only a running TwinCAT can answer

Work top to bottom: the order is by what breaks most if it is wrong. Write each result down as
you get it — two items recorded beat seven remembered.

**Rule 4 applies to you** (§12). You build the file; a person at the machine decides when it
is safe to press Record. The file below is five channels at 1 ms — 5 000 samples/s, inside
the `typical` load band — and is kept that small on purpose.

### 4.0 First: is the skill on this machine current?

The last session installed the skill globally (`~/.claude/skills/twincat-scope`) at commit
`1fa0e9b`. That copy still has every generator defect listed above, and testing it re-finds
them — the third session did exactly that. Pull it (or re-clone) and check that
`py -3 scripts/tcscope.py newscope --help` lists `--theme`.

### 4.1 Does a generated file record? — the one that matters

Pick five symbols from Scope View's own symbol browser, so the names are known to resolve:
**two members of one NC axis measuring the same thing** (its actual and set position) and
**three PLC variables: one `BOOL`, one `INT` or enum, one `LREAL`**.

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o Test.tcscopex \
    --netid <the target's AmsNetId> --sample-time-ms 1 --record-time 120 \
    --channels "<axis actual>,<axis set>,<plc bool>:BOOL,<plc int>:INT,<plc lreal>:LREAL"
py -3 scripts/tcscope.py checkscope Test.tcscopex
```

What `newscope` should report: the two axis channels on port 501 and the three PLC ones on
851; types `REAL64`, `REAL64`, `BIT`, `INT16`, `REAL64` with sizes 8, 8, 1, 2, 8; five
different names, none of them `Signal`. If the axis symbols are `Axes.<axis>.<field>`, the
two axis channels are typed from the NC table (`type_source: nc-field`) and nothing is listed
under `types_defaulted`; a PLC-side copy such as `MAIN.fbAxis.NcToPlc.ActPos` is listed there
instead — expected. `checkscope` should say `ok: true` with one warning, about a fixed window
and no trigger.

Open `Test.tcscopex` by **adding it to an existing TwinCAT Measurement project** — the last
session found that double-clicking one starts a new-project wizard that hangs — and have
someone record for a few seconds.

- **PASS:** it opens, and all five channels plot real, moving data.
- **If any channel does not:** copy Scope View's exact error text, then do 4.2 — it becomes
  the most important thing in the session.

While it is open, note the layout. Three guesses in the generator rest on it:

- a) Do the axis channels and the PLC channels arrive on **separate tabs**, one per device?
- b) Inside a tab, are different quantities drawn as **bands stacked one above another**?
  The PLC tab is where to look: the `BOOL` and the `INT` share a state band and the `LREAL`
  gets its own. The axis tab holds a single position band.
- c) Do the axis's actual and set position draw as **two traces over one shared Y axis**, in
  two different colours?

Describe what one chart actually looks like. If (c) is no, drag two symbols into one chart by
hand, save, and copy the `AxisGroup` XML Scope View wrote — that XML is the whole answer.

### 4.2 Compare against a file Scope View wrote itself

Do this even if 4.1 passed: a field-by-field comparison is how the last session found that the
type vocabulary was wrong, and nobody has audited the template's other fields since.

Open a `.tcscopex` from the same project that was authored in Scope View and is known to
record. Take one `AdsAcquisition` from it and the same kind from `Test.tcscopex` — an axis
channel against an axis channel, a `BOOL` against a `BOOL` — and list **every child element
whose value differs**, and every element present in one and not the other. Keep element
names and values such as types, sizes, ports and flags; replace names and addresses (§11).

### 4.3 Dark theme — do the new colours load, and look right?

Generated files looked like near-white panels in TwinCAT's dark theme. `newscope` now writes a
dark style by default (`--theme light` for the other): `#252526` on every `YTChart`,
`AxisGroup` and `OverviewChart`; an `AxisStyle` inside every axis's `SubMember`, as real files
have, with `#F1F1F1` axis text and a quiet `#3E3E42` grid; and a palette colour on each
`Channel` and its `ChannelStyle` alike. The `AxisStyle` is structure Scope has never been
given by this tool.

1. **Does `Test.tcscopex` still load, and record,** with the `AxisStyle` elements in it? If it
   is refused, that is the finding — copy the error.
2. With TwinCAT in dark theme, describe the chart background, the band backgrounds, the axis
   text, the grid and the traces. Then switch to light theme and describe them again. Is
   anything drawn in black and lost on the dark background — markers, the cursor, a legend?
3. Select one axis's style in the property grid. **What choices does `ColorMode` offer?**
   Every real file seen says `CustomColor`; another option may follow the theme.
4. Copy the file and, in the copy, delete every `AxisStyle` and the `<DisplayColor>` child of
   every `YTChart`, `AxisGroup` and `OverviewChart`. Open it in dark theme, then in light.
   Does it still load? Does Scope now choose colours that suit each theme?

If 3 or 4 finds that Scope can follow the theme, a mode that leaves the colours out beats both
palettes; if not, the palettes stand.

### 4.4 A real trigger

In Scope View, configure an actual trigger on `Test.tcscopex` — a `BOOL` going true is enough
— save it as `Test-trigger.tcscopex`, and run `checkscope` on that.

- **PASS:** `trigger_configured: true`, and the fixed-window warning is gone.
- **If it still says false:** copy the XML of the `TriggerModule` node, names replaced. That
  is all the fix needs.

Also check that `record_seconds` says 120 and that Scope View shows a 120 s window. That is
the second, independent confirmation that `RecordTime` counts 100 ns ticks.

### 4.5 `.svdx` → CSV with the real export tool

Save the recording from 4.1 as an `.svdx`, then:

```bash
py -3 scripts/tcscope.py doctor
uv run scripts/tcscope.py ingest <recording>.svdx -o rec.parquet
```

`doctor` should find `TC3ScopeExportTool.exe`; note the folder it reports below the TwinCAT
install root. `ingest` runs it as `TC3ScopeExportTool.exe svd=<file> target=<file.csv>
silent` — an argument form taken from documentation and **never executed**.

- **PASS:** a `.csv` appears next to the `.svdx`, and `rec.parquet` is written.
- **If it fails:** get the tool to export by hand and write down the exact command line that
  worked. The corrected invocation is the deliverable.

### 4.6 The round trip

On the CSV from 4.5:

```bash
uv run scripts/tcscope.py manifest <recording>.csv
uv run scripts/tcscope.py stats <recording>.csv
uv run scripts/tcscope.py events <recording>.csv
uv run scripts/tcscope.py correlate <recording>.csv --channels "<axis actual>,<axis set>"
```

- **PASS:** the columns carry the five names `newscope` chose, not `Signal`; units, sample
  rate and duration match what Scope View showed.
- `correlate` has never run on real data. Report what it says about actual against set
  position — including a refusal, if the two land in different acquisition groups.

### 4.7 The compiled symbol table (`.tmc`)

The structure was reported by an earlier session, and `checkscope --tmc` was built from it
without ever reading a real file. This is its first run against one. **Do not copy the `.tmc`
off the machine**: it is the program's whole symbol table.

```bash
uv run scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o tmc-check.tcscopex \
    --channels "<a BOOL>,<an enum>,<an LREAL>,<a DINT, left undeclared>,<a misspelt symbol>,<an FB instance>"
uv run scripts/tcscope.py checkscope tmc-check.tcscopex --tmc <path to the PLC>.tmc
```

- **PASS:** `tmc.resolved` counts the first three; the enum's `compiled_type` is its base
  type; the undeclared `DINT`, the misspelt symbol and the FB instance are each a problem.
- **Also try** one member of a library type (a `Tc2_MC2` `AXIS_REF` field, say) and one array
  element. Report whether each resolved, warned or failed, with the message, names replaced.

### 4.8 Does Scope keep a `<Comment>`?

`newscope` knows when it guessed a type, but the guess is invisible once the file is written —
a guessed `REAL64` and a declared one are byte-identical. The candidate place to record it is
the empty `<Comment>` in each `AdsAcquisition`.

In a copy of `Test.tcscopex`, put `tcscope:type=default` into one `AdsAcquisition`'s
`<Comment>`. Open it in Scope View, change something trivial, save. Does the text survive in
the saved file? Is it shown anywhere in the UI? Does the file still load?

### 4.9 A parked axis — if there is time

`events` reports `clipping` on an axis parked at the end of its travel, because a rest
position and a rail look the same in the data (§8). If there is time, record about 30 s with
an axis parked and — if the machine has one — a channel that genuinely saturates. Keep the
CSVs on the machine. Report `stats` and `events` for those channels, names replaced.

### 4.10 Does the agent pick the skill up? — needs no TwinCAT

Install the skill the way `README.md` says for Claude Code, open a folder containing a
`.tcscopex` or `.svdx`, and ask something like "why did the axis fault".

- **PASS:** the agent uses the skill without being told its name.
- **If not:** note the client version. That is a packaging problem, not a code one — do not
  patch the skill for it.

The GitHub Copilot install path is the same files in `.github/skills/` and has never been
observed working. Try it too if a Copilot licence is at hand; nobody on this project has one.

### What to bring back from Part A

Anything that failed, plus:

1. Scope View's error text for any channel that did not record, and the element diff from 4.2.
2. A description of one chart's layout, and the `AxisGroup` XML if 4.1 (c) failed.
3. The dark-theme answers from 4.3.
4. The `TriggerModule` XML, if 4.4 failed.
5. The working export-tool command line.
6. The `checkscope --tmc` output from 4.7, names replaced.
7. Whether `<Comment>` survived, from 4.8.

Every open task waiting on a machine closes from those seven.

# Part B — against the 19 real exports

Only if the exports from the earlier review (`evals/field-review-af54888.md`) are on this
machine.

## 5. THE critical check

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

## 6. What changed, and what to check

### 6.1 `events` — rewritten (this was the critical defect)

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

### 6.2 `window` — was double-counting

It indexed raw file rows rather than distinct time instants, so on a repeat-padded group it
printed every sample twice under one timestamp, and its `--max-rows` cap was evaluated against
padding — biting at half the promised width. It now reads distinct instants like every other
verb.

Check on a padded group: no two consecutive rows share a timestamp, and row count matches the
group's `n_samples` over the same span.

### 6.3 `stats` — one new field

`n_samples` per channel, so a standard deviation can be audited against how many points it was
computed over. `stats` was already de-duplicating correctly; this only makes it visible.

### 6.4 `checkscope` — acquisition load is now graded

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

### 6.5 Scale — now measured

`tests/make_scale_fixture.py` generates a large export (never committed);
`tests/bench_scale.py` reports wall clock and peak RSS per verb. Measured on a small Linux
container, 20 channels in two groups:

| Samples | File | Per verb | Peak RSS |
|---|---|---|---|
| 0.4 M | 5.7 MB | ~1 s | 108 MB |
| 2 M | 28.6 MB | ~4 s | 125 MB |
| 10 M | 143.6 MB | 15–24 s | 215 MB |
| 20 M | 288.3 MB | 31–33 s | 384 MB |

Peak memory tracks the **samples**, not the file: roughly 100 MB + 2 × the float64 array. The
CSV is read a chunk at a time, split exactly as `str.splitlines()` splits the whole file.
Also measured: one 13.6 s `ingest` turns that 143.6 MB CSV into 11 MB of Parquet, after which
the same verbs run in 1.8–3.3 s instead of 15–16 s.

Worth confirming on real hardware, since these numbers came from a constrained container:

```bash
python3 tests/make_scale_fixture.py --rows 500000 -o scale.csv
python3 tests/bench_scale.py scale.csv
```

## 7. Acceptance criteria

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

## 8. Known limitations — already understood, not bugs to re-report

- **`clipping` fires on an axis parked at the end of its travel.** A rest position and a rail
  are identical in the data. Requiring the signal to leave the rail and return was tried and
  defeated by LSB dither — a parked channel produced 427 separate runs at its rail. Left as a
  documented limitation rather than shipping an unvalidated heuristic. **If you can suggest a
  discriminator that survives the real files, that is the single most useful thing you could
  add.** A candidate is the speed at which the signal enters and leaves the rail.
- **Peak RSS is still ~2 × the array**, because the parsed blocks and the array they are
  joined into are alive at once. Copying block by block and freeing each was tried and saved
  nothing: the allocator kept the memory.

## 9. Verified correct — do NOT "fix" these

Both were checked against the raw bytes of the source files and are now regression-tested.

- **Symbol names truncated mid-parenthesis.** Beckhoff's own exporter writes them that way, and
  every symbol under the affected axis is truncated identically. The reader is being faithful.
  Do not add parenthesis-balancing.
- **`unit: "(None)"`.** The literal string TwinCAT writes in the Unit metadata row. Do not
  coerce it to `null`. Round-tripping what the source says beats guessing what it meant.

## 10. Not yet tested by anyone

State this in your report if you do not get to it — the skill's own rules require saying what
was not checked rather than implying coverage.

First, every item of Part A you did not reach — name them. Beyond Part A:

- `ingest` to Parquet against a real *large* export; only the generated scale fixture has
  been used.
- Label readability on `plot`. The verb has now run on real exports and made a 40k-sample
  overview readable in one image; nobody reported on full symbol paths at fontsize 8.
- `doctor` on a machine *without* `TC3ScopeExportTool.exe`. On the one machine it has run on
  it found the tool and reported the path correctly.

## 11. Rules for your report — please read, this one bit us

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
- **Project files, the `.tmc` and every recording stay on the machine.** Report element names
  and values such as types, sizes, ports and flags; replace symbol paths, channel names and
  net IDs.
- **Describe rather than screenshot.** A screenshot carries every channel name in its legend
  and axis labels. Showing one to the maintainer privately is fine; it never goes in the repo.
- **Tool paths below the TwinCAT install root only.** A path under a user profile names a
  person.

Report as a file in the repo (`evals/field-review-<sha>.md`, following the existing one's
shape) or as a message — either is fine, but keep it anonymised in both.

## 12. Safety rules this skill operates under

These are not negotiable and apply to you while testing:

1. **Never author safety logic** — no TwinSAFE, no FSoE, no safety-PLC configuration.
2. **Never write to or activate a live machine.** Reading measurements is safe. Writing a
   variable, activating a configuration, or switching Run/Config mode is a human gesture —
   propose the command, do not run it.
3. **Never claim something is verified that you have not verified.** Say what you did not check.
4. **Recorded data never goes into git.** It is large, it does not diff, and it carries real
   machine behaviour.
