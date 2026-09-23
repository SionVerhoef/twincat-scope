# Templates

Known-good `.tcscopex` scope projects. UTF-8 with BOM, CRLF, valid GUID linkage, and they
pass `scripts/tcscope.py checkscope`.

| File | What it is |
|---|---|
| `minimal-single-channel.tcscopex` | The smallest thing that records: one `AdsAcquisition`, one wired display `Channel`, one axis group. The base to build from. Its `SymbolName` is `PLACEHOLDER.Symbol`, so `checkscope` **deliberately fails** on it until you fill it in. |
| `axis-diagnosis.tcscopex` | Five channels on one servo axis at 1 ms, in one tab of four stacked bands: set and actual position together, then following error, velocity and torque. The default starting point for "why did this axis misbehave", and the worked example of the layout `newscope` writes. |

## Use them through the script, not by copying

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbAxis.NcToPlc.PosDiff:LREAL" \
    --netid 192.168.1.10.1.1 --sample-time-ms 1

py -3 scripts/tcscope.py checkscope MyScope.tcscopex
```

`py -3` is the Windows launcher, and TwinCAT runs on Windows; on Linux or macOS (and in this repo's CI) the same commands are `python3`.

**Copying a template file duplicates its GUIDs, and a project with duplicate identifiers is
invalid.** `newscope` mints fresh ones and — the part that is easy to get wrong — rewrites the
`AcquisitionGUID` references so each display channel still points at its own data source.
Re-GUIDing without that step produces a project that opens perfectly and plots nothing.

`newscope` also clones the matching display channel per symbol, so asking a one-channel
template for four channels gives four visible traces rather than four invisible acquisitions.

The templates supply the *style* — axis settings, chart options, byte conventions — while
`newscope` decides the *layout*: a chart tab per device and a stacked band per quantity, so
requesting twenty channels does not produce twenty traces sharing one axis. See
`references/scope-configuration.md` → *Layout*.

## What the templates deliberately show

- `SymbolBased` is `true` and `IndexGroup`/`IndexOffset` are `0`. Symbolic addressing survives
  a rebuild; direct addresses do not, and silently read the wrong memory afterwards.
- `AmsNetId` is `0.0.0.0.0.0`, a placeholder `checkscope` warns about. A real NetID committed
  to a shared repository identifies a specific controller and will be wrong for everyone else.
- `UseTaskSampleTime` is `false` with `BaseSampleTime` set explicitly, so the templates
  demonstrate the units. **`BaseSampleTime` is in 100 ns ticks** — 10000 is 1 ms. For real
  work, prefer `UseTaskSampleTime` = `true`; see `references/recording-load.md`.
- `DataType` is `REAL64` with `VariableSize` 8 — Scope's own type names, not IEC ones. Scope
  reads `LREAL` as `VOID` and refuses the channel, and `checkscope` refuses both. Change type
  and size together or the values are garbage.
- `TargetPort` is 851 in both, and that is right for their symbols: `MAIN.fbAxis.NcToPlc.…`
  is the PLC's own copy of the axis data. Only symbols under `Axes.` live in the NC runtime on
  501, and `newscope` routes those itself.
- Every axis carries an `AxisStyle` for the dark theme, where real projects keep one.
  `newscope --theme` recolours the chart panels, axes, grid and traces; the other elements
  keep the template's `Black` (chart style, marker container, trigger, acquisitions). Whether
  Scope draws anything with those is not known — markers on a dark chart are worth a look.

## Verification status

These were written from a schema derived by reading real Beckhoff sample projects. **Neither
template has been opened in TwinCAT as shipped.** Files `newscope` generated from
`axis-diagnosis.tcscopex` have: the first opened and recorded nothing
(`evals/field-review-1fa0e9b.md`); with the type, name and port fixes, and later with the
`AxisStyle` elements and dark theme as shipped here, they recorded NC axis and PLC channels
unedited (`evals/field-review-1fa0e9b-rounds.md`, `evals/field-review-fe9b487.md`). If you
load one, whether it works or fails, that is worth reporting back — and open it by adding it
to an existing Measurement project, not by double-clicking it.
