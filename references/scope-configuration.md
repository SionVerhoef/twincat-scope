# `.tcscopex` — anatomy of a scope project

Configuration only. A `.tcscopex` holds *what to record and how to draw it*, with no measured
data — which is what makes it templatable, diffable and safe to commit. Recorded data lives in
`.svdx` (and `.svd` before TwinCAT 3.3.3140).

**Verification status:** this schema was derived by reading real Beckhoff sample projects. A
file generated from it first opened and recorded nothing (`evals/field-review-1fa0e9b.md`);
with the type, name and port fixes described below, files generated unedited **record** — NC
axis channels on 501, and PLC `BIT`, `INT16` and `REAL64` channels on 851, with an
`AxisStyle` on every axis (`evals/field-review-fe9b487.md`) — and a trigger configured in
Scope View on a generated file was detected by `checkscope` and recorded
(`evals/field-review-3e4c44d.md`).

**What Scope rewrites on first save** is listed in `evals/field-review-3e4c44d.md`: it drops
`IsFileBased`/`Suffix`, fills unit and style blocks, and keeps one time-axis `AxisStyle` per
tab. None of it affects loading or recording, and a saved file is the one to diff against.
Scope also fills an empty PLC acquisition's `<Comment>` with the variable's declaration
comment, so that field is not free for PLC channels.

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
that a newer Scope View upgrades an older project rather than rejecting it. **So far:** files
generated from `axis-diagnosis.tcscopex`, which keep its `1.0.0.0`, loaded in TE130x Scope
View in both field sessions (builds not recorded) — every error came later, at connect — and
one recorded. If a template is
refused on yours, raising `Version` to match a project your installation writes is the first
thing to try.

**Open a generated file by adding it to an existing Measurement project.** Double-clicked on
its own, one started a new-scope-project wizard and hung; added to a project, it opened at
once.

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

**Seen in Scope View:** a one-tab, four-band layout arrived exactly as written — `Position`
{ActPos, SetPos}, `Following error`, `Velocity`, `Torque / current` — and a file with three
`YTChart` siblings arrived as three tabs (`evals/field-review-1fa0e9b-rounds.md`,
`evals/field-review-fe9b487.md`).

## Colours

Every colour is absolute: a signed 32-bit ARGB integer (`-921103` is `0xFFF1F1F1`) or a .NET
colour name (`Black`). Scope draws them as written: a dark-styled generated file stayed dark
with the IDE in dark theme and in light (`evals/field-review-fe9b487.md`). Whether it would
theme a colour the file leaves out is untested, so `newscope` writes them all and a file is
styled for one background. What each one is taken to colour — **read from the structure; the
dark theme was seen working as a whole, not checked element by element**:

| Element | Its `DisplayColor`, as read |
|---|---|
| `YTChart`, `AxisGroup`, `OverviewChart` | the panel behind the traces. The light greys `newscope` used to write here were the reported glare, which fits; `OverviewChart` has not been seen |
| `TimeAxis` / `ValueAxis` → `SubMember/AxisStyle` | axis text; `GridColor` is the grid. `ColorMode` is `CustomColor` in every real file seen |
| `Channel` and its `ChannelStyle` | the trace. Which of the two Scope draws with is not established, so `newscope` writes both |

Real projects carry an `AxisStyle` on **every** axis, time and value alike; files from older
versions of `newscope` carry none, and `checkscope` says so. `newscope --theme dark` (default)
writes a `#252526` background with `#F1F1F1` axis text — the values a real dark-styled project
uses — and `--theme light` a near-white one. The trace palette is stepped per background and
checked for contrast against it; its first four are also checked for colour-blind separation
between every pair, because every trace in a band shares one axis. With five or more in a band
some pairs are close, and the channel name is what separates them. A light chart in a dark IDE
was reported from the field as glaring; the dark default read well with the IDE in both
themes. The generated `AxisStyle` matched one Scope wrote element for element, the grid colour
aside, and Scope accepted it on every axis.

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
| `BaseSampleTime` | **100 ns ticks.** 10000 = 1 ms, 1000 = 100 µs — confirmed a second way when Scope saved 80000 and the recording ran at 125 Hz. Only honoured when `UseTaskSampleTime` is `false`, and **Scope snaps it to a multiple of the owning task's cycle**: 100000 (10 ms) on a 4 ms task was saved as 80000 (8 ms). |
| `UseTaskSampleTime` | `true` samples at the owning task's rate — usually what you want. See `recording-load.md`. |
| `Oversample` | For oversampling terminals. `0` unless the hardware supports it. |

Project-level, `RecordTime` is also in 100 ns ticks — `600000000` is 60 seconds, which is what the templates ship. `newscope --record-time <seconds>` sets it. A window shorter than the event you are after is a wasted trip: a homing sequence or a slow startup can outrun 60 s on its own.

## Generating one

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos:LREAL,MAIN.fbStation.sbBlocked:BOOL,Axes.Axis1.ActPos" \
    --netid 192.168.1.10.1.1 --port 851 --sample-time-ms 1 --record-time 120

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

For `Axes.<axis>.<field>`, the NC runtime's own field names say their type, because Beckhoff
fixes them: `ActPos`, `SetPos`, `PosDiff`, `ActVelo`, `SetVelo`, `ActAcc`, `SetAcc`,
`ActTorque`, the `…Modulo` positions and `Position` are `REAL64`; `ErrState`, `ErrorCode`,
`ErrorID`, `AxisState` and `CoupleState` are `UINT32`. Every such acquisition in the nine files
of one real project agrees, and `newscope` writes them that way with `type_source: nc-field`
— unless the entry declares a type, names a port other than 501, or has a deeper path, and
`checkscope` warns when a file disagrees with the table. No `UINT32` channel has recorded yet.

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
  wrapper rather than a device (`NcToPlc`, `PlcToNc`, `Status`, `Inputs`…), so
  `MAIN.fbAxis1.NcToPlc.ActPos` is grouped under `fbAxis1`. Two devices whose paths end in
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
- **Flags in lanes.** Two flags in one band sit on the same two levels and hide each other,
  and Scope saves no band height to give them room — resizing a band in Scope View changed
  no field in the file. So each `BIT` in a `Digital / state` band gets a display offset of
  1.5 × its position (`Channel/SubMember/AcquisitionInterpreter/Offset`). That moves only
  the drawn trace: a flag at offset 2 exported only 0 and 1, and the CSV's `Offset` header
  row recorded the 2. The axis reads the offset value, not the flag's own.
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
sample rate high enough to perturb the target, axes with no `AxisStyle`, and acquisitions,
bands or channels with `Enabled` false. Disabling is a Scope View feature, so that is not a
failure — but a file with every band disabled showed nothing until they were enabled by hand,
and whether a disabled acquisition still records has not been established.

It also prints the layout — every chart, its bands and their channels — and warns when a chart
stacks more than six bands or a band overlays more than eight channels. Both are readability,
not validity: the file is fine, the picture is not. `theme` says which background the charts
are styled for: `dark`, `light`, `mixed`, or `null` when they use named colours.

Run it every time before handing a file to a human.
