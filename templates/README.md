# Templates

Known-good `.tcscopex` scope projects. UTF-8 with BOM, CRLF, valid GUID linkage, and they
pass `scripts/tcscope.py checkscope`.

| File | What it is |
|---|---|
| `minimal-single-channel.tcscopex` | The smallest thing that records: one `AdsAcquisition`, one wired display `Channel`, one axis group. The base to build from. Its `SymbolName` is `PLACEHOLDER.Symbol`, so `checkscope` **deliberately fails** on it until you fill it in. |
| `axis-diagnosis.tcscopex` | Four channels on one servo axis — position, velocity, torque, following error — at 1 ms. The default starting point for "why did this axis misbehave". Generated from the minimal template with `newscope`. |

## Use them through the script, not by copying

```bash
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbAxis.NcToPlc.PosDiff" \
    --netid 192.168.1.10.1.1 --sample-time-ms 1

python3 scripts/tcscope.py checkscope MyScope.tcscopex
```

**Copying a template file duplicates its GUIDs, and a project with duplicate identifiers is
invalid.** `newscope` mints fresh ones and — the part that is easy to get wrong — rewrites the
`AcquisitionGUID` references so each display channel still points at its own data source.
Re-GUIDing without that step produces a project that opens perfectly and plots nothing.

`newscope` also clones the matching display channel per symbol, so asking a one-channel
template for four channels gives four visible traces rather than four invisible acquisitions.

## What the templates deliberately show

- `SymbolBased` is `true` and `IndexGroup`/`IndexOffset` are `0`. Symbolic addressing survives
  a rebuild; direct addresses do not, and silently read the wrong memory afterwards.
- `AmsNetId` is `0.0.0.0.0.0`, a placeholder `checkscope` warns about. A real NetID committed
  to a shared repository identifies a specific controller and will be wrong for everyone else.
- `UseTaskSampleTime` is `false` with `BaseSampleTime` set explicitly, so the templates
  demonstrate the units. **`BaseSampleTime` is in 100 ns ticks** — 10000 is 1 ms. For real
  work, prefer `UseTaskSampleTime` = `true`; see `references/recording-load.md`.
- `DataType` is `LREAL` with `VariableSize` 8. Change both together or the values are garbage.

## Verification status

These were written from a schema derived by reading real Beckhoff sample projects. **They have
not been opened in TwinCAT.** They are structurally faithful and unproven — if you load one
successfully, or it fails, that is worth reporting back.
