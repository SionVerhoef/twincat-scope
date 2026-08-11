# Changelog

## Unreleased

First working version. Not yet published.

### Analysis

- `manifest`, `stats`, `events`, `plot`, `window`, `correlate` — a ladder of verbs that
  summarise a recording instead of returning samples from it.
- `plot` draws a **min/max envelope per pixel bucket** rather than decimating, so a
  three-sample spike survives a 22:1 reduction instead of having a 1-in-7 chance of showing up.
- `window` caps its row count and refuses to widen, so a broad question cannot flood a context
  window by accident.
- CSV reader sniffs delimiter and decimal separator, handling the European `;` + `,` export
  that would otherwise parse `1,5` as `15`.
- `ingest` converts `.svdx` and CSV to Parquet once, via `TC3ScopeExportTool.exe` where needed.

### Acquisition

- `newscope` writes a `.tcscopex` with freshly minted GUIDs, cloning both the acquisition and
  its matching display channel per requested symbol, and rewriting `AcquisitionGUID` so each
  channel still points at its own data source.
- `checkscope` validates GUID uniqueness, resolves every `AcquisitionGUID`, and warns when the
  total sample rate is high enough to perturb the machine being measured.
- `doctor`, `newscope` and `checkscope` need no third-party packages, so acquisition works on a
  machine that has never seen `uv`.

### Documentation

- `references/data-triage.md` — the method: why samples never enter the conversation, and why
  envelopes beat decimation.
- `references/recording-load.md` — a recording is not free; propose it, let a human start it.
- Four hard rules in `SKILL.md`: no safety logic, no writes to a live machine, no unverified
  claims, and — specific to measurement — a recording is not free.

### Known gaps

- **Nothing has been opened in TwinCAT.** The `.tcscopex` schema is derived from real Beckhoff
  sample projects; the templates are structurally faithful and unproven.
- **The CSV reader has never seen genuine `TC3ScopeExportTool.exe` output.** It sniffs and
  reports what it detected. One real exported CSV closes this.
- `BaseSampleTime` is documented as 100 ns ticks, confirmed from a sample's `RecordTime`, but
  not verified against a second independent source.
