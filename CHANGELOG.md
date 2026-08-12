# Changelog

## Unreleased

First working version. Not yet published.

### Reading real Scope exports

Measured against 19 genuine `TC3ScopeExportTool.exe` exports from a Beckhoff CX/AX8000
machine. The reader had been written from assumptions and was wrong about the file's basic
shape: it failed outright on the TAB dialect and was silently wrong on most of the rest.

- **A Scope CSV is a horizontal concatenation of acquisition groups**, each with its own
  time column and often its own sample rate — so a physical row is not one instant in time.
  The reader now parses the group layout from the metadata rows, and every channel is
  timestamped from its own group's clock. Forcing group 0's axis on everything was wrong by
  2–10 ms on repeat-padded exports and by up to 31 seconds on unpadded ones.
- **Delimiter election prefers `;`, then TAB, then `,`.** On a European TAB export every row
  holds as many decimal commas as TABs, so a consistency-only vote elected `,`, collapsed
  the column count and reported no numeric rows at all.
- **Decimal separator is scored over data rows**, not inferred from the delimiter — the TAB
  dialect is a EU export and nothing about a TAB says so.
- **A data row must be entirely numeric.** Metadata rows are key/value pairs and so exactly
  50% numeric, which the old "at least half" rule accepted as data.
- **Channel names come from `SymbolName`, else `Name`**, never from a metadata value row —
  which is how every channel in a TAB export ended up named `0`. Channels expose both a
  short `name` (the selector) and the qualified `symbol_name`.
- **Group time columns are no longer reported as data channels**, so a 0-to-20280 time ramp
  stops appearing in stats, events and correlations.
- `manifest` reports per-group sample time (declared and measured), `repeat_factor`, span
  and NaN count, plus a `timing` block: `row_is_one_instant`, `max_skew_ms` and
  `cross_group_timing_valid`. An export whose groups were never repeat-padded is flagged as
  broken, and cross-group claims on it are refused rather than averaged away.
- Times are read as milliseconds and reported as seconds throughout.
- Blank cells inside the data block no longer fabricate values: NaN stays NaN instead of
  becoming a real reading of `0.0`, so a gap is not reported as a step or a flatline, and a
  blank in a time column no longer poisons the measured rate.
- `correlate` normalises before correlating, documents its lag sign (negative means `a`
  leads `b`), uses each group's own `dt`, and refuses cross-group pairs unless
  `--allow-cross-group` is passed. `--max-lag-samples` now bounds the lag search rather than
  truncating the recording to its first N samples.
- `window` returns one block per group; rows from different groups are never merged under a
  single timestamp.
- `ingest` stores the group layout in the Parquet schema metadata, so per-group time axes
  survive the round trip, and no longer drops columns that share a channel name.
- `plot` labels the y-axis with the short name and the qualified path in the title, labels
  time in seconds, and gives groups with different rates their own x-axis.
- `checkscope` warns about acquisitions wired to no display channel, reports shared
  `AcquisitionGUID`s instead of counting past the acquisition total, notes acquisitions with
  no declared `BaseSampleTime` that the load figure therefore omits, and no longer counts
  the null GUID as a duplicate. The load warning drops from 100 000 to 20 000 samples/s: the
  densest real project measured 16 250, so the old line never fired.
- `tests/make_real_fixtures.py` regenerates structural copies of all five real layouts, and
  the suite covers group counts, channel counts, per-group rates, repeat factors, skew,
  blank cells, cross-group refusal, the Parquet round trip, and a planted step proved
  against each group's own time axis.

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
- **No `.svdx` has been converted by the real export tool here.** The CSV path is measured
  against 19 real exports, but the `.svdx` → CSV step still depends on
  `TC3ScopeExportTool.exe` behaving as documented.
- The `;` delimiter appeared in none of the 19 real files. It stays supported on the strength
  of the synthetic EU fixture alone.
- `BaseSampleTime` is documented as 100 ns ticks, confirmed from a sample's `RecordTime`, but
  not verified against a second independent source.
