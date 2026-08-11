# `.tcscopex` — anatomy of a scope project

Configuration only. A `.tcscopex` holds *what to record and how to draw it*, with no measured
data — which is what makes it templatable, diffable and safe to commit. Recorded data lives in
`.svdx` (and `.svd` before TwinCAT 3.3.3140).

**Verification status:** this schema was derived by reading real Beckhoff sample projects. It
has not been round-tripped through TwinCAT. Treat it as accurate about structure and
unproven about acceptance.

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
that a newer Scope View upgrades an older project rather than rejecting it. **That assumption
is untested.** If a template is refused, raising `Version` to match a project your
installation writes is the first thing to try.

## Structure

```
ScopeProject                     AssemblyName="TwinCAT.Measurement.Scope.API.Model"
└── SubMember
    ├── DataPool                 what is sampled          Suffix .svdp
    │   └── SubMember
    │       └── AdsAcquisition   ONE PER CHANNEL          Suffix .svacq
    ├── YTChart                  how it is drawn          Suffix .svchart
    │   └── SubMember
    │       ├── AxisGroup                                 Suffix .svagroup
    │       │   └── SubMember
    │       │       ├── TimeAxis / ValueAxis              Suffix .svaxis
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

## `AdsAcquisition` fields that matter

| Field | Notes |
|---|---|
| `SymbolName` | The PLC symbol path, e.g. `MAIN.fbAxis.NcToPlc.ActPos`. Used when `SymbolBased` is `true`. |
| `SymbolBased` | `true` = resolve by name (portable). `false` = use `IndexGroup`/`IndexOffset`, which are addresses and break when the program is rebuilt. Prefer `true`. |
| `IndexGroup` / `IndexOffset` | Direct addresses. Leave `0` when symbol-based. **Never copy these between machines.** |
| `TargetPort` | `851` for the first PLC runtime. `852`, `853`… for further ones. |
| `AmsNetId` | The target. A placeholder here is the single most common reason a scope records nothing. |
| `DataType` | `LREAL`, `REAL`, `INT16`, `DINT`… Must match the symbol, or values are garbage. |
| `VariableSize` | Bytes: 8 for LREAL, 4 for REAL/DINT, 2 for INT16. Keep consistent with `DataType`. |
| `BaseSampleTime` | **100 ns ticks.** 10000 = 1 ms, 1000 = 100 µs. Only honoured when `UseTaskSampleTime` is `false`. |
| `UseTaskSampleTime` | `true` samples at the owning task's rate — usually what you want. See `recording-load.md`. |
| `Oversample` | For oversampling terminals. `0` unless the hardware supports it. |

Project-level, `RecordTime` is also in 100 ns ticks — `600000000` is 60 seconds.

## Generating one

```bash
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbAxis.NcToPlc.PosDiff" \
    --netid 5.68.118.43.1.1 --port 851 --sample-time-ms 1

python3 scripts/tcscope.py checkscope MyScope.tcscopex
```

`newscope` clones the template's acquisition **and its matching display channel** for each
symbol, re-GUIDs both, and wires them together. Requesting four channels from a one-channel
template therefore yields four plotted traces, not four invisible acquisitions.

Neither verb needs third-party packages, so this works on a machine with only Python.

## `checkscope`

Reports a **problem** (exit 1) for anything that makes the project invalid or silently empty:
duplicate GUIDs, an unfilled `PLACEHOLDER` symbol, a dangling `AcquisitionGUID`, no
acquisitions at all.

Reports a **warning** for things that are legal but probably not what you meant: a placeholder
`AmsNetId`, no display channel wired to anything, and a total sample rate high enough to
perturb the target.

Run it every time before handing a file to a human.
