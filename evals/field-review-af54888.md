# Field review — main @ af54888

Run by an agent on a Beckhoff commissioning workstation against **19 genuine TwinCAT Scope
CSV exports** from a live packaging machine (SmartTrak linear-motor track, AX8640 drives,
TC3.1) and **7 real `.tcscopex` project files** from a production TwinCAT Measurement
project. Windows, Python 3.12.10, numpy 2.5.2, matplotlib 3.11.1, pyarrow 25.0.1,
`TC3ScopeExportTool.exe` present, `uv` absent so scripts were invoked directly.

**None of those files are in this repo and none can be.** They are customer machine data.
This document is the only record of their shape, which is why it is kept.

## Verdict

The group-model rewrite is correct. `tests/test_verbs.py` 79/79 passed; 19/19 exports matched
hand-derived ground truth exactly on ncols, group count, channel count, row count and
`max_skew_ms`; every defect from the previous remediation spec (D1–D9, D11–D13) was closed
and verified on real data rather than on fixtures.

Confirmed on real data:

| Check | Result |
|---|---|
| Time columns excluded from channels | `ncols == len(groups) + len(channels)` on all 19 files |
| Qualified names | `name` and `symbol_name` both populated; no channel named after a metadata key |
| Comma dialect | `time_unit=ms`, `estimated_rate_hz=500.0` (was 0.5) |
| Declared vs measured | `sample_time_ms_declared/measured` + `repeat_factor` agree on every file |
| Broken export | `max_skew_ms=31150.0`, `cross_group_timing_valid=false` |
| `--allow-cross-group` on the broken export | Still refuses |
| `checkscope` | Unwired-acquisition and no-trigger warnings fire correctly on all 7 real projects |

> That last refusal is the single best behaviour in the tool. Do not soften it.

## Ground truth — the 19 files

Groups are (n_channels) per group. MAX_SKEW is `timing.max_skew_ms`.

| File | Delim | Dec | ncols | Data line | Groups | Chans | Rows | MAX_SKEW |
|---|---|---|---|---|---|---|---|---|
| Project.csv | `,` | `.` | 34 | 8 | 14/15/2 | 31 | 10141 | 10 |
| Project1.csv | TAB | `,` | 76 | 24 | 38×1 | 38 | 15577 | 31150 |
| Project3.csv | TAB | `,` | 76 | 24 | 38×1 | 38 | 15577 | 31150 |
| Project11.csv | TAB | `,` | 56 | 24 | 24/30 | 54 | 5393 | 2 |
| Project1223.csv | `,` | `.` | 19 | 8 | 6/11 | 17 | 2939 | 2 |
| Project123/12345/2/222/44/7/91/99.csv | `,` | `.` | 37 | 8 | 14/18/2 | 34 | 6031–25039 | 10 |
| Project5.csv | TAB | `,` | 50 | 24 | 25×1 | 25 | 5339 | 0 |
| Projectccc/ttt.csv | `,` | `.` | 42 | 8 | 14/23/2 | 39 | 12613/19465 | 10 |
| Projectqqqq.csv | `,` | `.` | 40 | 8 | 14/21/2 | 37 | 7663 | 10 |
| Projectxxxx.csv | `,` | `.` | 40 | 8 | 25/13 | 38 | 16875 | 2 |
| Festo Project1.csv | TAB | `,` | 120 | 40 | 60×1 | 60 | 47247 | 0 |

Acquisition load across the 7 real projects: SmartTrak 16 250, Indexer 11 667, Double_Pusher
7 750, SmartTrakHoming 5 750, PusherAxes 4 000, CaseLift_n_Tipper 2 750, Capacity 417
samples/s.

Largest genuine export: 43.8 MB, 47 247 rows × 120 columns, 60 channels @ 250 Hz —
`manifest` 3.42 s, `stats` 3.63 s, `events` 5.63 s.

## Findings, and what was done

### F1 — `events` was unusable on real machine data (critical)

Measured firing rates, `--max-events 100000`:

| File | Rows | Chans | Duration | Events | Per channel |
|---|---|---|---|---|---|
| Project11 | 5393 | 54 | 10.8 s | 9209 | 170 |
| Project | 10141 | 31 | 20.3 s | 3082 | 99 |
| Project91 | 25039 | 34 | 50.1 s | 11558 | 340 |
| Projectxxxx | 16875 | 38 | 33.8 s | 15690 | 413 |

Split by data type: REAL64 298.6/channel, BIT 10.1, INT16 11.6. Worst were all motion
signals — ActVelo2B 1627, ActVelo1B 1120, ofPositionAxis2B 939. The reviewer disproved the
obvious hypothesis that repeat-padding caused it: group 0 (`repeat_factor=1`) fired 244.6
events/channel against group 1's (`repeat_factor=2`) 111.3.

Root cause: **MAD of the first difference degenerates on a piecewise-constant signal.** An
axis at rest has over half its differences at the encoder's quantisation floor, so MAD
collapses to ~1e-9 — non-zero, so it passed the `if not mad` guard — and `6·MAD·1.4826`
became a threshold every acceleration sample cleared.

Compounded by chronological truncation: `found.sort(key=time)[:100]` returned the first 100
events, covering 0.1% of Project11's recording while reporting `ok: true`.

| File | Returned | Of | Window covered |
|---|---|---|---|
| Project11 | 100 | 9209 | 0.1% |
| Project91 | 100 | 11558 | 12.7% |
| Project | 100 | 3082 | 22.8% |
| Projectxxxx | 100 | 15690 | 33.1% |

**Done.** `tests/fixtures/real/real_comma_atrest.csv` reproduces the shape — an axis parked
for 60% of the recording, one commanded move, one planted disturbance. On it the old
detector produced 713 events, 601 from the position channel, with the planted fault outside
the default 100. Fixed by flooring the threshold at a fraction of the channel's own travel
(`--min-step`), coalescing each sustained excursion into **one** event, naming wide
excursions `ramp` so `step` still means a discontinuity, exempting two-valued channels from
the analogue detectors, and ranking worst-first within each tenth of the recording. Result:
**11 events, worst channel 4, planted disturbance ranked first.**

### F2 — `window` double-counted repeat-padded rows

`cmd_window` indexed `group["time"]` directly rather than `group["instants"]`, so a
`repeat_factor=2` group emitted every sample twice under one timestamp, and the `--max-rows`
cap was evaluated against padded rows — biting at half the real width.

**Done.** `window` now reads distinct instants like every other verb. `stats` was checked and
was already correct (it goes through `Recording.samples`), but now reports `n_samples` so
that is auditable from the output rather than by reading the source.

### F3 — nothing had ever tested the scale claim

**Done.** `tests/make_scale_fixture.py` generates the file (never committed);
`tests/bench_scale.py` measures wall clock and peak RSS. Budget is in
`references/data-triage.md`. Peak memory tracked the file at 5.5×, because `load_csv` built a
Python list of lists of floats for the whole export before handing it to numpy. Parsing now
runs in chunks: **785 → 340 MB at 10 M samples, and 30% faster.** Sniffing and line indexing
were left untouched, and old-vs-new `manifest` output is byte-identical on all 8 fixtures.

### F4 — `LOAD_WARN_SAMPLES_PER_S` never fired

Correct, and it was still true after the previous round lowered it to 20 000 — the densest
real project is 16 250.

**Done.** Replaced with bands taken from the seven measured projects, so the figure means
something at every value and the densest real projects land in a band that says so. Tested in
both directions.

## Verified correct — do not "fix" these

Both were checked against the raw bytes of the source files and are now regression-tested.

- **Truncated symbol names.** `Axes.Smarttrak M2 (E1_101U2_ChB.ActTorque` is missing its
  closing parenthesis in Beckhoff's own export, and every symbol under that axis is truncated
  identically. Do not add paren-balancing.
- **`unit: "(None)"`.** The literal string TwinCAT writes in the Unit metadata row. Do not
  coerce it to null.

## Not checked by this review

Stated explicitly, per the skill's own reporting contract: `plot` (label readability with
full symbol paths at fontsize 8 remains unverified), `ingest` to Parquet against a real
44 MB export, `newscope`, `doctor` on a machine without the export tool, and memory at any
scale. Nothing was written to or activated on any live controller, and no `.tcscopex` project
files were modified.

## Still open

- `clipping` fires on an axis parked at the end of its travel — a rest position and a rail
  are identical in the data. Documented as a known limitation; needs the real exports to
  test a discriminator against.
- Peak RSS is still ~2.2× the file size, because the decoded text and its line list are alive
  at once. Streaming needs an exact byte offset out of `sniff_csv` first.
