# Field review — `de1162b` and `fe9b487`, Part A of the brief

Two reports from one test workstation on 2026-09-23 — the same Windows machine, TwinCAT 3,
TE130x Scope View and TF3300 Scope Server as `field-review-1fa0e9b-rounds.md`. The first ran
`de1162b` against a function-block recording built earlier; its findings became `fe9b487`,
which the second report then ran through §4 of `evals/field-test-brief.md`. The skill was a
plain copy of main, checked by `newscope --help` listing `--theme` and `checkscope` printing
`disabled`.

**Anonymised.** Axis, device, symbol and file names are stand-ins — the axis is
`Axes.Axis 1 (Drive1_ChA)`, PLC symbols are `GVL.fbStation.*` by role. The first report
arrived carrying a project number, a product name, the controller's address and full symbol
paths; none of them is here. Counts, rates, sizes, ports and colour values are as measured.

Generated files were added to an existing Measurement project, not double-clicked, and a
person pressed Record.

## Verdict

**This version's own output records.** A generated file with an `AxisStyle` on every axis
opened and recorded five NC axis channels with no hand edits, and a mixed file recorded the
first bit, integer and PLC channels a generated file has produced. Both were built by
`newscope` and checked by `checkscope` exactly as shipped.

## Part A, item by item

### 2 — round 3 on main's own output: PASS

Five NC channels of one axis — `SetPos`, `ActPos`, `PosDiff`, `ActVelo`, `ActTorque` — at 1 ms.
`newscope`: all on port 501, `REAL64`/8, `type_source` `nc-field`, nothing defaulted, theme
dark; one tab of four bands (Position 2, Following error 1, Velocity 1, Torque / current 1).
`checkscope`: `ok`, load typical, nothing disabled, one warning — a fixed window with no
trigger. Scope View opened it with no error and recorded. Its 8 `AxisStyle` elements, one per
time and value axis of four bands, were accepted.

### 3 — colours: partly answered

The charts looked right with the IDE in dark theme and in light; they stayed dark in both,
which the user found acceptable. So Scope draws the stored colours as written and does not
follow the IDE theme for this file. Nothing was reported lost or unreadable, though markers,
cursor and legend were not checked one by one.

Offline, one of our `AxisStyle` elements matched one written by Scope element for element; only
`GridColor` differed (Scope `-921103`, ours `-12698046`, which is `#3E3E42` by design). The
Scope-authored files carry 76 of them across 9 files.

**Not done:** the `ColorMode` options in the property grid, and the omission test — a copy
without any `AxisStyle` or panel `DisplayColor` was built and passed `checkscope`, but was
not opened.

### 4 — first bit, integer and PLC channels: PASS

`Axes.Axis 1 (Drive1_ChA).ActPos`, `.SetPos`, and a PLC `BOOL`, `INT` enum and `LREAL`.
`newscope`: ports 501, 501, 851, 851, 851; types `REAL64`, `REAL64`, `BIT`, `INT16`, `REAL64`;
sizes 8, 8, 1, 2, 8; `nc-field` for the axis pair, `declared` for the PLC three. Three tabs —
the axis (Position 2); one function block (Digital / state 1); another (Position 1, the
`LREAL`, and Step / count 1). `checkscope` `ok` with one warning. **All five recorded moving
data.** Three tabs from three `YTChart` siblings, as laid out.

### 5 — a function-block recording, regenerated: layout PASS

What the first report found on `de1162b`, from 32 channels of a sequencer with nested
function blocks in a prefix-style house (`se`/`sb`/`sf`/`sn`/`on`):

- Names were unique; the file built with `1fa0e9b` had called all 32 `seStep`.
- A step enum and counters shared the digital axis with seven flags, a length named for a
  loading zone was filed under torque, and one band held 9 traces, drawing `checkscope`'s
  crowding warning against `newscope`'s own layout. All three fixed in `fe9b487`.
- The older file had every `AxisGroup` `Enabled` false and showed nothing until they were
  enabled by hand. Neither version writes `Enabled`, so it was edited after `newscope`; by
  what is not confirmed. `checkscope` now warns about it.

On `fe9b487` the list had grown to 40 channels — 39 PLC and one virtual axis's `ActPos` —
generated at 10 ms: 4 000 samples/s, load typical. `checkscope` `ok`, nothing disabled, no
crowding warning; the widest band held exactly 8 traces, so the split did not trigger.

| Tab | Bands |
|---|---|
| parent sequencer | Step / count 1 |
| start-up block | Digital / state 8, Step / count 3, Other 2 (lengths) |
| track block, ×2 | Position 4, Digital / state 2, Step / count 3, Other 3 (lengths) |
| recipe struct | Digital / state 1 |
| virtual axis | Position 1 |

Recording this file was not confirmed; the layout was reviewed. Two findings from the user:

- **A.** In the track tabs, two `BOOL`s in a band sized like the others are hard to read.
- **B.** The parent sequencer's step gets a tab to itself, and a step is read against what it
  drives, not alone. The recipe struct's single `BOOL` has the same problem.

Lengths not named as positions landed in `Other`, as designed.

### 4.2 — generated against Scope-authored, field by field

For an axis `ActPos` and a PLC `BOOL` from the same project:

| | Scope-authored | Generated |
|---|---|---|
| only in one | `CompressionMode` `Uncompressed`, `SaveOption` `IncludeDataInSVDX`, `UTF8Encoding` false, an empty `SubMember`, a full `RawUnit`/`UserUnit` block | `IsFileBased` false, `Suffix` `.svacq`, `RawUnit`/`UserUnit` as a leaf reading `false` |
| `UseTaskSampleTime` | true | false |
| `BaseSampleTime` | 20000 (axis), 40000 (PLC) | 10000 |
| `SortPriority` | 11 | 10 |
| `FileHandle` | 2 | 0 |

None of these stopped a recording — items 2 and 4 recorded with them. Left as they are: the
structure that recorded is now known, and aligning it would reopen that.

### 4.5 — export tool

`doctor` found `TC3ScopeExportTool.exe` under the TwinCAT root in
`Functions\TF3300-Scope-Server\`. `ingest` was not run: no `.svdx` was saved.

### 4.7 — the compiled symbol table

A PLC's `.tmc`, read in place and not copied off the machine:

- Symbols at `TcModuleClass/Modules/Module/DataAreas/DataArea/Symbol`, children `Name`,
  `BitSize`, `BaseType`, `Properties`, `BitOffs`.
- A function block's `DataType` has `BitSize`, `Method`, `Name`, `Properties`, `SubItem`; each
  member `SubItem` has `Name`, `Type`, `Comment`, `BitSize`, `BitOffs`, `Default` — the same
  shape for `BOOL`, `INT` and `LREAL`.
- An enum's `DataType` has `Name`, `Comment`, `BitSize`, `BaseType`, `Properties` and an
  `EnumInfo` (`Text`, `Enum`); the underlying type is `BaseType`. 803 data types, 140 enums,
  on `INT` 121, `UINT` 10, `DWORD` 3, `BYTE` 2, `USINT` 2, `DINT` 1, `UDINT` 1.

## Not checked

`ColorMode` and the omission test; a real trigger (4.4); `ingest` (4.5); the round trip
(4.6); whether Scope keeps a `<Comment>` (4.8); a parked axis (4.9); VS Code and Copilot
(4.10); and all of Part B — the 19 exports are not on this machine.
