# `.tcscopex` — anatomy of a scope project

Configuration only. A `.tcscopex` holds *what to record and how to draw it*, with no measured
data — which is what makes it templatable, diffable and safe to commit. Recorded data lives in
`.svdx` (and `.svd` before TwinCAT 3.3.3140).

This schema was derived by reading real Beckhoff sample projects. Files generated from it,
unedited, record NC axis channels on 501 and PLC `BIT`, `INT16` and `REAL64` channels on 851
(`evals/field-review-fe9b487.md`).

**What Scope rewrites on first save:** it drops `IsFileBased`/`Suffix`, fills unit and style
blocks, and keeps one time-axis `AxisStyle` per tab. None of it affects loading or recording,
and a saved file is the one to diff against. Scope also fills an empty PLC acquisition's
`<Comment>` with the variable's declaration comment; a hand-written comment replaces it,
survives a save, and is what the CSV export's `SymbolComment` row then carries.

**Saving in XAE: name the menu item.** After edits in the scope's Properties grid, Ctrl+S may
not reach the scope editor and the changes are lost. Tell the user *File → Save
<name>.tcscopex* with the scope's node selected in Solution Explorer, not "save the project".

## Byte conventions

Match them or the file may not load, and will certainly produce a noisy diff:

- **UTF-8 with BOM** (`EF BB BF`)
- **CRLF** line endings
- `<?xml version="1.0" encoding="utf-8"?>`

`.gitattributes` in this repo sets `*.tcscopex -text` so git never rewrites the line endings
regardless of `core.autocrlf`. `scripts/tcscope.py` writes both conventions.

## The schema is versioned

`ScopeProject/Version` is not decoration. Across real sample projects it ranges from
`1.0.0.0` to `1.0.0.6`, and the newer ones carry more elements — 216 distinct tags versus
196 in an older sibling. Newer TwinCAT writes newer projects.

The templates here declare `1.0.0.0`, the most conservative value observed, on the assumption
that a newer Scope View upgrades an older project rather than rejecting it. Generated files
with `1.0.0.0` have loaded in every field session so far. If a template is refused on yours,
raising `Version` to match a project your installation writes is the first thing to try.

**Open a generated file by adding it to an existing Measurement project.** Double-clicked on
its own, one started a new-scope-project wizard and hung; added to a project, it opened at
once.

**Save the recording before changing any setting.** Changing a scope's settings after Record
discards the unsaved recording. And Save only writes a `.tcscopex` Scope regards as modified:
pressed on an unchanged scope it leaves the file untouched, so a file's timestamp does not say
Scope has re-serialised it.

## Structure

```
ScopeProject                     AssemblyName="TwinCAT.Measurement.Scope.API.Model"
└── SubMember
    ├── DataPool                 what is sampled          Suffix .svdp
    │   └── SubMember
    │       └── AdsAcquisition   ONE PER CHANNEL          Suffix .svacq
    ├── YTChart                  ONE PER TAB              Suffix .svchart
    │   └── SubMember
    │       ├── AxisGroup    ONE PER STACKED BAND     Suffix .svagroup
    │       │   └── SubMember
    │       │       ├── TimeAxis / ValueAxis              Suffix .svaxis
    │       │       │   └── SubMember
    │       │       │       └── AxisStyle    axis text and grid colours
    │       │       ├── MarkerContainer                   Suffix .svmc
    │       │       └── Channel  ONE PER PLOTTED SIGNAL   Suffix .svchannel
    │       │           └── SubMember
    │       │               ├── AcquisitionInterpreter    Suffix .svai
    │       │               └── ChannelStyle              Suffix .svstyle
    │       ├── OverviewChart / ChartStyle
    └── TriggerModule                                     Suffix .svtm
```

Every node carries a `<Guid>`.

## The part that bites: acquisition and display are linked by GUID

`DataPool/AdsAcquisition` says *what to sample*. `YTChart/.../Channel` says *what to draw*.
They are separate trees, joined by exactly one field:

```
Channel → SubMember → AcquisitionInterpreter → <AcquisitionGUID>
                                                     ↓  must equal
                        AdsAcquisition → <Guid>
```

Two consequences worth internalising:

- **Copying a template duplicates GUIDs.** A project with duplicate identifiers is invalid.
  `newscope` mints fresh ones; do not hand-copy a template file.
- **Re-GUIDing naively breaks the link.** Replacing every `<Guid>` and stopping there leaves
  `AcquisitionGUID` pointing at an identifier that no longer exists. The project then opens
  perfectly and plots *nothing* — the worst failure mode available, because it looks fine
  until someone presses Record on a machine they had to stop to get access to.

`refresh_guids()` in `scripts/tcscope.py` builds an old→new map and rewrites every element
whose text matches, whatever its tag, so references travel with their targets.
`checkscope` verifies afterwards that every `AcquisitionGUID` resolves.

## Layout: what shares a tab, a band and an axis

Wiring decides whether a channel is *recorded*. Layout decides whether anyone can *see* it,
and it is the easier of the two to get wrong without noticing, because the file passes every
structural check either way.

Three levels, and the middle one is the one people skip:

| Element | On screen | Consequence |
|---|---|---|
| `YTChart` | one tab | Tabs cost nothing. Use them. |
| `AxisGroup` | one band stacked inside that tab, with its own time and value axis | Bands share the tab's height, so six is about the limit before each is too thin to read. |
| `Channel` | one trace inside that band | **Everything in a band shares one auto-scaled Y axis.** |

That last line is the whole problem. Put a following error of 0.02 mm on the same axis as a
position of 1200 mm and the error is drawn as a flat line on zero — recorded perfectly,
present in the export, invisible on screen. Twenty channels in one band is twenty traces
fighting over one axis, most of them flat.

So group by what the axis has to do:

- **Same quantity, same order of magnitude → same band.** Set and actual position belong
  together; the gap between them is usually the thing being looked at. Same for two axes'
  torque when comparing them, or a set/actual velocity pair.
- **Different quantity → different band.** Position, following error, velocity, torque and a
  handful of booleans on one axis is five different scales and no useful picture.
- **Different device → different tab.** One tab per axis, per drive, per station.

`ChartStyle/StackedAxes` says whether a chart's bands are drawn one above another. `newscope`
sets it `true` whenever it writes more than one band and `false` for a single-band chart,
which has nothing to stack. Channels sharing a band are also given different `DisplayColor`
values, because two traces of the same colour on one axis is the same failure by another
route.

Scope View draws the layout exactly as written: a one-tab, four-band file arrives as four
stacked bands, and three `YTChart` siblings arrive as three tabs.

**Change a layout by regenerating, not by editing the XML.** A hand-edited file with every
band disabled shows nothing until someone enables the bands in Scope View. If you must edit
one, copy an element that is enabled, and run `checkscope` again afterwards.

## Colours

Every colour is absolute: a signed 32-bit ARGB integer (`-921103` is `0xFFF1F1F1`) or a .NET
colour name (`Black`). Scope draws them as written: a dark-styled generated file stayed dark
with the IDE in dark theme and in light. Whether it would
theme a colour the file leaves out is untested, so `newscope` writes them all and a file is
styled for one background. What each one is taken to colour — **read from the structure; the
dark theme was seen working as a whole, not checked element by element**:

| Element | Its `DisplayColor`, as read |
|---|---|
| `YTChart`, `AxisGroup`, `OverviewChart` | the panel behind the traces; `OverviewChart` has not been seen |
| `TimeAxis` / `ValueAxis` → `SubMember/AxisStyle` | axis text; `GridColor` is the grid. `ColorMode` is `CustomColor` in every real file seen; Scope View offers Custom, First Channel, or one named channel of the band — none follows the IDE theme |
| `Channel` and its `ChannelStyle` | the trace. Which of the two Scope draws with is not established, so `newscope` writes both |

Real projects carry an `AxisStyle` on **every** axis, time and value alike, and `checkscope`
warns about an axis without one. `newscope --theme dark`
writes a `#252526` background with `#F1F1F1` axis text — the values a real dark-styled project
uses — and `--theme light` a near-white one. The trace palette is stepped per background and
checked for contrast against it; its first four are also checked for colour-blind separation
between every pair, because every trace in a band shares one axis. With five or more in a band
some pairs are close, and the channel name is what separates them.

The default, `--theme auto`, follows the TwinCAT XAE Shell: it reads `ColorTheme` under
`HKCU\Software\Beckhoff\TcXaeShell\<version>\ApplicationPrivateSettings\Microsoft\VisualStudio`
(`0*System.String*<GUID>`), which changes the moment the IDE's theme does — Dark gives `dark`,
Light and Blue give `light`. The IDE's `.vssettings` file is not used: it lags until the IDE
exits. Where the value cannot be read — TwinCAT inside a full Visual Studio, a custom theme,
another OS — it falls back to `dark`, because a light chart in a dark IDE glares while a dark
chart reads well in both. `theme_source` says which happened. Found on TcXaeShell 15.0.

## `AdsAcquisition` fields that matter

| Field | Notes |
|---|---|
| `SymbolName` | The PLC symbol path, e.g. `MAIN.fbAxis.NcToPlc.ActPos`. Used when `SymbolBased` is `true`. |
| `SymbolBased` | `true` = resolve by name (portable). `false` = use `IndexGroup`/`IndexOffset`, which are addresses and break when the program is rebuilt. Prefer `true`. |
| `IndexGroup` / `IndexOffset` | Direct addresses. Leave `0` when symbol-based. NC axis channels recorded that way, although real files carry non-zero values on their NC acquisitions — Scope does not need them as inputs. **Never copy these between machines.** |
| `TargetPort` | `851` for the first PLC runtime. `852`, `853`… for further ones. **NC axis symbols (`Axes.…`) are served by the NC runtime on `501`.** One port written across every channel resolves the PLC symbols and fails every axis symbol with "Symbolname could not be found" — a message that sends you looking at the name, which is not the problem. |
| `AmsNetId` | The target. A placeholder here is the single most common reason a scope records nothing. |
| `DataType` | Scope's own vocabulary, **not IEC's**: `BIT` for a `BOOL`, `INT16` for an `INT`, `REAL64` for an `LREAL`. Seen in real project files: `BIT`, `INT8`, `INT16`, `UINT32`, `REAL64`; the others follow the same naming. Scope read `LREAL` as `VOID`, **wrote `VOID` back when the project was saved**, and refused the channel: "The datatype is not supported: 'VOID'". Other IEC names are expected to go the same way; only `LREAL` has been tried. A `VOID` in a file is that failure's fingerprint. |
| `VariableSize` | Bytes, and it must match `DataType`: 1 for `BIT`/`INT8`, 2 for `INT16`, 4 for `UINT32`, 8 for `REAL64`. Scope reads that many bytes from the target whatever the variable actually is, so 8 bytes off a `BOOL` is a recording of its neighbours. |
| `Name` | The label in the Scope tree **and the column header when the recording is exported to CSV**. `minimal-single-channel.tcscopex` ships the placeholder `Signal`; left alone, fifty-three channels exported as fifty-three columns called `Signal`, which is what happened on a machine. `newscope` derives a short unique name per channel and keeps the full path in `Title`. |
| `BaseSampleTime` | **100 ns ticks.** 10000 = 1 ms, 1000 = 100 µs — confirmed a second way when Scope saved 80000 and the recording ran at 125 Hz. Only honoured when `UseTaskSampleTime` is `false`. **Keep it a multiple of the owning task's cycle.** Measured: Scope snaps it **when recording starts** — not on load or Save — to the cycle of **each acquisition's own task**, **rounding down** to a whole multiple, and a value **below one cycle becomes one cycle**. No message is shown. 75000 (7.5 ms) recorded at 4 ms on a 4 ms PLC task and 6 ms on a 2 ms NC task in one file; 1, 5000 and 30000 all recorded at one cycle; 80000 on the 4 ms task stayed 80000. The Properties grid and the `.tcscopex` show the written value until the next save after a recording; the `.svdx` carries the value used. |
| `UseTaskSampleTime` | `true` samples at the owning task's rate — usually what you want. See `recording-load.md`. |
| `Oversample` | For oversampling terminals. `0` unless the hardware supports it. |

Project-level, `RecordTime` is also in 100 ns ticks — `600000000` is 60 seconds, which is what the templates ship. `newscope --record-time <seconds>` sets it. A window shorter than the event you are after is a wasted trip: a homing sequence or a slow startup can outrun 60 s on its own.

## Generating one

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos:LREAL,MAIN.fbStation.sbBlocked:BOOL,Axes.Axis1.ActPos" \
    --netid 1.2.3.4.1.1 --port 851 --sample-time-ms 1 --record-time 120

py -3 scripts/tcscope.py checkscope MyScope.tcscopex
```

An entry is `SYMBOL`, `SYMBOL:TYPE` or `SYMBOL:TYPE:PORT`. The type is IEC (`BOOL`, `INT`,
`LREAL`) or Scope's own (`BIT`, `INT16`, `REAL64`); the port overrides the namespace rule and
is how a second PLC runtime (852, 853…) is reached per channel. Fields are read from the
right and only when they are recognisable — a digits-only tail is a port, a known name is a
type — and anything else is refused rather than guessed at, so a mistyped type is an error
instead of part of a symbol name. No TwinCAT symbol path seen here contains a colon, but
nothing in the format promises that, and a symbol that does contain one cannot be written in
this grammar.

The NC runtime's own field names say their type, because Beckhoff fixes them. Two shapes are
typed, and `newscope` writes them with `type_source: nc-field`:

- **`Axes.<axis>.<field>`**, the fields Scope View's symbol browser lists on an axis: the
  positions, velocities, accelerations, torques, `PosDiff`, `SetJerk`, `CtrlOutput`,
  `DriveOutput` and `TorqueOffset` are `REAL64`; `AxisState`, `CoupleState`, `ErrState`,
  `CmdNo`, `ControlDWord`, `HomingState`, `OverrideV` and `StateDWord` are `UINT32`.
- **`Axes.<axis>.ToPlc.<field>`** and **`Axes.<axis>.FromPlc.<field>`**, the axis's copies of
  the [`NCTOPLC_AXIS_REF`](https://infosys.beckhoff.com/content/1033/tcplclib_tc2_mc2/70133899.html)
  and [`PLCTONC_AXIS_REF`](https://infosys.beckhoff.com/content/1033/tcplclib_tc2_mc2/70138507.html)
  structs of Tc2_MC2, typed member by member (`ErrorCode`
  and `AxisState` `UINT32`, `CmdNo` `UINT16`, `ModuloActTurns` `INT32`…). Members that are
  structs or arrays are not typed.

**`ErrorCode` is not a field of the axis.** Scope refused `Axes.<axis>.ErrorCode` as an unknown
symbol on a real NC; recorded as `Axes.<axis>.ToPlc.ErrorCode` it read back as `UINT32`
integers. `newscope` names the `ToPlc` path under `nc_paths_suspect`, and `checkscope` warns,
for any such struct member written directly on the axis. The axis field list is one NC on
TwinCAT 3.1 4024.55; another build may expose more.

An entry that declares a type, names a port other than 501, or has any other path keeps its own
type, and `checkscope` warns when a file disagrees with the tables.

Any other channel given no type is written as `REAL64` and **listed in the output as
defaulted**, because a default is a guess and guessing wrong on a `BOOL` records nothing
usable. `--port`
sets the PLC port for every channel that does not name its own; anything under `Axes.` goes
to the NC runtime on 501 unless a channel overrides it.

`newscope` clones the template's acquisition **and its matching display channel** for each
symbol, re-GUIDs both, and wires them together. Requesting four channels from a one-channel
template therefore yields four plotted traces, not four invisible acquisitions.

It also lays them out, rather than piling every trace onto one axis:

- **One tab per device.** The symbol path minus its leaf, minus the structs that describe a
  wrapper rather than a device (`NcToPlc`, `PlcToNc`, the NC's own `ToPlc` and `FromPlc`,
  `Status`, `Inputs`…), so `MAIN.fbAxis1.NcToPlc.ActPos` is grouped under `fbAxis1` and
  `Axes.Axis1.ToPlc.AxisState` under `Axis1`. Two devices whose paths end in
  the same segment keep their full paths as titles rather than merging into one tab.
- **One band per quantity inside that tab**, ordered position, following error, velocity,
  acceleration, torque/current, pressure, temperature, digital state, step / count, other.
  The quantity is read from the leaf name, so `PosDiff` is a following error rather than a
  position and `bPosReached` is a state rather than either. Where the name says nothing — a
  house that writes `seStep` and `sbBlocked` matches no keyword at all — the **declared type**
  decides: bits band as digital state, and integers as step / count, rather than piling into
  `Other` on one axis. The two stay apart even when the name says "state": a step number
  running to 200 draws every 0/1 flag beside it as a flat line.
- **No band past eight traces.** A band that would hold more is split into even parts —
  `Digital / state`, `Digital / state (2)` — because that is where `checkscope` starts warning,
  and a generator should not write what its own checker complains about.
- **Flags stay on 0/1.** Scope saves no band height, so the file cannot give flags more room.
  A channel offset (`Channel/SubMember/AcquisitionInterpreter/Offset`, part of its scaling
  beside `ScaleFactor`) shifts the drawn trace — and the exported values too when *Scale
  values before export* is on — and flags stacked that way were too close to tell apart, with axis labels that no
  longer lined up. So `newscope` writes no offset, and colour tells flags in one band apart.
- **A lone parent is drawn beside what it drives.** A block with one channel and blocks
  beneath it — `GVL.fbCell.fbControl.seStep` above `…fbControl.fbStartup.*` — gets no tab of
  its own; the channel is drawn first in its band in each descendant's tab, as extra display
  channels on one acquisition, so it costs the target nothing more. A one-segment path (`GVL`,
  `MAIN`) is a namespace, not a block, and a lone block with nothing beneath it has no one to
  lend context to; both keep their tab. `checkscope` counts acquisitions drawn in several tabs
  and warns only when one is drawn twice in the same tab.
- **Tabs appear in the order the symbols were asked for**, because that ordering is
  information.

The grouping is a naming heuristic and will not know every house convention; anything it
cannot place lands in an `Other` band, visible and clearly labelled rather than silently
misfiled. `newscope` prints the layout it wrote, so it can be checked before the file is
handed over. `--layout flat` puts everything back on one axis for the case where the channels
genuinely share a scale.

Neither verb needs third-party packages, so this works on a machine with only Python.

## `checkscope`

Reports a **problem** (exit 1) for anything that makes the project invalid, silently empty or
unable to record: duplicate GUIDs, an unfilled `PLACEHOLDER` symbol, a dangling
`AcquisitionGUID`, no acquisitions at all, an NC symbol on a PLC port, a `TargetPort` that is
not an ADS port, an IEC type name where Scope's own vocabulary belongs, a `VOID` type (Scope
has opened this file and could not read the type it was given), a `VariableSize` that
contradicts its `DataType`, and acquisitions that share a name or carry none — those export as
columns nobody can tell apart.

Reports a **warning** for things that are legal but probably not what you meant: a placeholder
`AmsNetId`, a PLC symbol on a port below 851 where no runtime answers, a channel still
carrying the template's placeholder name, no display channel wired to anything, a total
sample rate high enough to perturb the target, a fixed recording window (no trigger, or
`TriggerAction` `NONE`, and no `AutoRestartRecord`), axes with no `AxisStyle`, and acquisitions,
bands or channels with `Enabled` false. Disabling is a Scope View feature, so that is not a
failure — but a file with every band disabled showed nothing until they were enabled by hand,
and whether a disabled acquisition still records has not been established.

When the PLC project is at hand, add `--tmc <PLC>.tmc` — the compiled symbol table the build
writes beside the `.plcproj` (repeat it for a second PLC runtime). Every PLC symbol is then
looked up in the compiled program: a typo, a renamed variable, a whole block or an unindexed
array is a problem, and so is a type read at the wrong width — an undeclared `DINT` written
as `REAL64`. Enums are read at their base type. A type the `.tmc` does not describe, such as
one from a library, is a warning, never a guess. The reader was written from the structure of
one real `.tmc` and has been run against one (862 symbols, `evals/field-review-49a8e9b.md`);
on another program, treat a surprising result as a finding about the reader.

It also prints the layout — every chart, its bands and their channels — and warns when a chart
stacks more than six bands or a band overlays more than eight channels. Both are readability,
not validity: the file is fine, the picture is not. `theme` says which background the charts
are styled for: `dark`, `light`, `mixed`, or `null` when they use named colours.

Run it every time before handing a file to a human.
