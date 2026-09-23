# Field review — `3e4c44d`, round 5: export, trigger, and what Scope saves

The same test workstation as `field-review-fe9b487.md`, on 2026-09-23, running main at
`3e4c44d` (PR #16: a parent block's lone step drawn in each child block's tab). A plain copy,
checked by `checkscope` printing `acquisitions_in_several_tabs`. A person pressed Record;
nothing was written to the machine.

**Anonymised.** Names are stand-ins, as in the earlier reviews; no NetID, project, product or
symbol path is here. Counts, sizes, rates and times are as measured.

Two recordings: **R1** untriggered, 45.1 s; **R2** triggered, with a display offset set,
15.5 s.

## Verdict

The full path works: a generated file recorded, the real export tool converted the `.svdx`
with the documented command line on its first run, and `ingest` and `manifest` read the
result. A trigger configured in Scope View was detected by `checkscope`. One design fault
came out — a channel drawn in three tabs exports three times — and is fixed in the reader.

## 1 — the function-block file, regenerated and recorded: PASS

The same 40 channels at `--sample-time-ms 10`. No tab for the parent sequencer; its step drawn
first in `Step / count` in all three child tabs; the recipe struct and the virtual axis kept
their own. 5 tabs, 13 bands, 40 acquisitions, 42 display channels. `checkscope`: `ok`,
`acquisitions_in_several_tabs` 1, nothing disabled, load typical, one warning (fixed window).
Opened, recorded, and the tabs "look good" to the user; no further regrouping asked for.

The parent step was identical in all three tabs. In R2 it went 0 → 10 (565 samples at 0,
1 375 at 10); in R1 it held at 0. Channels that changed value: R1 6 of 42, R2 16 of 42.

**Scope saved 8 ms, not 10.** `BaseSampleTime` 100000 became 80000, and both recordings ran at
125 Hz. The motion task cycles at 4 ms, the others at 12 and 24 ms: Scope snaps a sample time
to a multiple of the owning task's cycle. It is also a second, independent confirmation that
`BaseSampleTime` is in 100 ns ticks — 80000 ticks, 8 ms, 125 Hz measured.

## 2 — `.svdx` → CSV → Parquet: PASS, and the fold duplicated in the export

`doctor` found `TC3ScopeExportTool.exe` under `Functions\TF3300-Scope-Server\`. `ingest`,
running `svd=<file> target=<file.csv> silent`, worked first time on both recordings — the first
real run of that command line. R1: `.svdx` 3.3 MB → CSV 3.2 MB → Parquet 1.4 MB.

The CSV was TAB-delimited with decimal commas, as five of the 19 earlier exports were.
`manifest`: 42 groups of one channel, 8.0 ms declared and measured, no gaps, no NaN times.

**The parent step was in the export three times** — `<name>`, `<name> (1)`, `<name> (2)`, each
in a group of its own, values and time columns identical, in both recordings. Scope exports a
column per display channel, not per acquisition: 42 columns for 40 acquisitions.

## 3 — a real trigger: PASS

A trigger on a `BOOL`, added in Scope View to the generated file itself. `checkscope`:
`trigger_configured` true, the fixed-window warning gone, `ok`, `record_seconds` 60. R2 ran
with it: 15.5 s, first sample at t = −0.002 s. Scope also created a `TriggerGroup_<n>\Images`
folder beside the project.

## 4 — band height and display offset: both answered

- **Band height is not saved.** One band enlarged in Scope View, its neighbour shrank; after
  saving, no field changed on any `AxisGroup` or `ValueAxis` in that tab. An `AxisGroup`'s own
  fields are `ChannelRelatedGuid`, `Comment`, `DisplayColor`, `Enabled`, `Guid`, `Name`,
  `ShowTitle`, `SortPriority`, `Title`.
- **A display offset moves only the drawing.** Offset 2 on one `BOOL`, saved as
  `Channel/SubMember/AcquisitionInterpreter/Offset` on the display channel. In R2's export the
  column held only 0 and 1 (1 646 × 0, 294 × 1); the CSV's `Offset` header row said 2 for it
  and 0 for every other.

## 5 — colours: Scope does not follow the IDE theme

A copy with no `AxisStyle` and no panel `DisplayColor` loaded, and its colours did not change
with the IDE theme — nor, in round 4, did a styled file's. The palettes stand. `ColorMode` was
not found in the property grid.

## 6 — `<Comment>`

A hand-written comment in an NC acquisition's `<Comment>` survived Scope's save. Scope filled
the empty `<Comment>` of 28 of 40 PLC acquisitions with the PLC declaration comment, so it is
not a free field for PLC channels. Whether it overwrites a hand-written one there is untested.

## What Scope rewrote on save

None of this stopped loading or recording.

- `IsFileBased` and `Suffix` removed everywhere.
- `RawUnit`/`UserUnit` and `ResultingUnit`/`UserUnit` filled with a full unit block where
  ours is a leaf reading `false`.
- Each acquisition given `CompressionMode` `Uncompressed`, `SaveOption` `IncludeDataInSVDX`,
  `UTF8Encoding` false and an empty `SubMember`.
- `ChannelStyle/SubMember` filled with `MinMaxStyle`, `SeriesStyle` (colour kept) and
  `TimeShiftStyle`.
- `ShowTitle` false added to each `AxisGroup`.
- `ChartStyle` filled with `ChartZoomStyle` and `ChartMenuStyle`; `ForeColor` `-921103` on the
  chart and `DarkSlateGray` on the overview chart.
- `AxisStyle` 26 → 18: one time-axis style kept per tab (5 of 13) and all 13 value-axis ones.
  Stacked bands share one time axis.

## What was done with it

- **Copies are read as one channel.** The reader collapses exact copies — same symbol and
  port, same time column, same values — and `manifest` reports `copies_collapsed`. Kept in
  Parquet.
- **A display offset is reported as `display_offset`** and never applied to values.
- **Flags stack in lanes.** `newscope` gives each `BIT` in a `Digital / state` band a display
  offset of 1.5 × its position, since there is no band height to set.
- **`newscope` notes the task-cycle snap** whenever `--sample-time-ms` is given.
- Not aligned with Scope's save: Scope rewrites all of it on first save, and none of it
  affected loading or recording.

## Not checked

`ColorMode`; whether Scope overwrites a hand-written PLC `<Comment>`; a parked axis (4.9); VS
Code and Copilot (4.10); all of Part B.
