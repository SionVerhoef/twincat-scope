# `.tcscopex` — anatomy of a scope project

Configuration only. A `.tcscopex` holds *what to record and how to draw it*, with no measured
data — which is what makes it templatable, diffable and safe to commit. Recorded data lives in
`.svdx` (and `.svd` before TwinCAT 3.3.3140).

**Verification status:** this schema was derived by reading real Beckhoff sample projects. A
file generated from it first opened and recorded nothing (`evals/field-review-1fa0e9b.md`);
with the type, name and port fixes described below, one **recorded** five NC axis channels
(`evals/field-review-1fa0e9b-rounds.md`). That covers `REAL64` NC channels only — bit,
integer and PLC-side channels, triggers and the `AxisStyle` colours have not been seen
working.

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
generated from `axis-diagnosis.tcscopex`, which keep its `1.0.0.0`, opened cleanly in TE130x
Scope View in both field sessions (builds not recorded), and one recorded. If a template is
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

**Seen in Scope View once:** a generated file's one-tab, four-band layout arrived exactly as
written — `Position` {ActPos, SetPos}, `Following error`, `Velocity`, `Torque / current`
(`evals/field-review-1fa0e9b-rounds.md`). Several `YTChart` siblings arriving as several tabs
is still the reading of the structure, not an observation.

## Colours

Every colour is absolute: a signed 32-bit ARGB integer (`-921103` is `0xFFF1F1F1`) or a .NET
colour name (`Black`). No value that follows the IDE theme has been seen, so a file is styled
for one background. Where each one lives:

| Element | Its `DisplayColor` is |
|---|---|
| `YTChart`, `AxisGroup`, `OverviewChart` | the panel behind the traces |
| `TimeAxis` / `ValueAxis` → `SubMember/AxisStyle` | axis text; `GridColor` is the grid. `ColorMode` is `CustomColor` in every real file seen |
| `Channel` and its `ChannelStyle` | the trace. Which of the two Scope draws with is not established, so `newscope` writes both |

Real projects carry an `AxisStyle` on **every** axis, time and value alike; files from older
versions of `newscope` carry none, and `checkscope` says so. `newscope --theme dark` (default)
writes a `#252526` background with `#F1F1F1` axis text — the values a real dark-styled project
uses — and `--theme light` a near-white one. The trace palette is stepped per background and
checked for contrast against it and for colour-blind separation between neighbours. A dark
chart still reads in a light IDE; a light one in a dark IDE was reported from the field as
glaring. **Not yet opened in Scope View.**

## `AdsAcquisition` fields that matter

| Field | Notes |
|---|---|
| `SymbolName` | The PLC symbol path, e.g. `MAIN.fbAxis.NcToPlc.ActPos`. Used when `SymbolBased` is `true`. |
| `SymbolBased` | `true` = resolve by name (portable). `false` = use `IndexGroup`/`IndexOffset`, which are addresses and break when the program is rebuilt. Prefer `true`. |
| `IndexGroup` / `IndexOffset` | Direct addresses. Leave `0` when symbol-based. NC axis channels recorded that way, although real files carry non-zero values on their NC acquisitions — Scope does not need them as inputs. **Never copy these between machines.** |
| `TargetPort` | `851` for the first PLC runtime. `852`, `853`… for further ones. **NC axis symbols (`Axes.…`) are served by the NC runtime on `501`.** One port written across every channel resolves the PLC symbols and fails every axis symbol with "Symbolname could not be found" — a message that sends you looking at the name, which is not the problem. |
| `AmsNetId` | The target. A placeholder here is the single most common reason a scope records nothing. |
| `DataType` | Scope's own vocabulary, **not IEC's**: `BIT` for a `BOOL`, `INT16` for an `INT`, `REAL64` for an `LREAL`. Seen in real project files: `BIT`, `INT8`, `INT16`, `UINT32`, `REAL64`; the others follow the same naming. Scope reads an IEC name such as `LREAL` as `VOID`, **writes `VOID` back when the project is saved**, and refuses the channel: "The datatype is not supported: 'VOID'". A `VOID` in a file is that failure's fingerprint. |
| `VariableSize` | Bytes, and it must match `DataType`: 1 for `BIT`/`INT8`, 2 for `INT16`, 4 for `UINT32`, 8 for `REAL64`. Scope reads that many bytes from the target whatever the variable actually is, so 8 bytes off a `BOOL` is a recording of its neighbours. |
| `Name` | The label in the Scope tree **and the column header when the recording is exported to CSV**. `minimal-single-channel.tcscopex` ships the placeholder `Signal`; left alone, fifty-three channels exported as fifty-three columns called `Signal`, which is what happened on a machine. `newscope` derives a short unique name per channel and keeps the full path in `Title`. |
| `BaseSampleTime` | **100 ns ticks.** 10000 = 1 ms, 1000 = 100 µs. Only honoured when `UseTaskSampleTime` is `false`. |
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

Under `Axes.`, the NC runtime's own field names say their type, because Beckhoff fixes them:
`ActPos`, `SetPos`, `PosDiff`, `ActVelo`, `SetVelo`, `ActAcc`, `SetAcc`, `ActTorque`, the
`…Modulo` positions and `Position` are `REAL64`; `ErrState`, `ErrorCode`, `ErrorID`,
`AxisState` and `CoupleState` are `UINT32`. Every real file seen agrees, and `newscope`
writes them that way with `type_source: nc-field`.

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
  acceleration, torque/current, pressure, temperature, digital state, other. The quantity is
  read from the leaf name, so `PosDiff` is a following error rather than a position and
  `bPosReached` is a state rather than either. Where the name says nothing — a house that
  writes `seStep` and `sbBlocked` matches no keyword at all — the **declared type** decides:
  bits and integers band as state rather than piling into `Other` on one axis.
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
sample rate high enough to perturb the target, and axes with no `AxisStyle`.

It also prints the layout — every chart, its bands and their channels — and warns when a chart
stacks more than six bands or a band overlays more than eight channels. Both are readability,
not validity: the file is fine, the picture is not. `theme` says which background the charts
are styled for: `dark`, `light`, `mixed`, or `null` when they use named colours.

Run it every time before handing a file to a human.
