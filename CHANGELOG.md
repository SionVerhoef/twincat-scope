# Changelog

## Unreleased

First working version. Not yet published.

### Triage that survives real machine data

A second field review on the same 19 genuine exports — kept in
`evals/field-review-af54888.md`, since the files themselves cannot be — confirmed the group
model is correct and found that `events` was not.

- **An excursion is one event, however long it lasts.** Reporting each over-threshold sample
  separately turned a single commanded move into 1199 "steps". Real exports fired 170–413
  events per channel; on the new at-rest fixture the count went from 713 to 11.
- **The detection threshold has a floor.** An axis at rest has a first-difference MAD of
  ~1e-9 — non-zero, so it passed the old zero-guard, and `6·MAD·1.4826` then flagged every
  acceleration sample. `--min-step` floors it at a fraction of the channel's own travel.
- **New event kinds `ramp` and `transition`**, so `step` keeps meaning a discontinuity worth
  explaining rather than "the machine moved". Two-valued channels are exempt from the
  clipping and flatline tests, which describe a BOOL wrongly in both directions.
- **Truncation is no longer chronological.** It returned the first 100 events — 0.1% of one
  recording — while the fault sat at 9 s. Events are now ranked worst-first within each tenth
  of the recording, and a `summary` totalling *every* event by kind, by channel and by time
  decile is always returned, truncated or not.
- **`window` reads distinct instants**, so a repeat-padded group no longer prints every
  sample twice under one timestamp with its row cap biting at half the promised width.
  `stats` reports `n_samples` so a standard deviation can be audited against what it covered.
- **Scale is measured rather than claimed.** `tests/make_scale_fixture.py` and
  `tests/bench_scale.py`; budget in `references/data-triage.md`. Chunked parsing cut peak
  memory from 785 MB to 340 MB at ten million samples and ran 30% faster; `manifest` output
  is byte-identical to the previous reader on every fixture.
- **Acquisition load is graded into bands** taken from seven real projects, replacing a
  threshold that sat above every project anyone had built and so never fired.
- **Regression-tested as correct**: symbol names truncated mid-parenthesis by Beckhoff's own
  exporter, and the literal unit string `(None)`.

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

### Measured against a no-skill baseline

`evals/` runs each prompt twice — once by an agent following this skill, once by an agent with
it withheld — and grades both mechanically. Iteration 1 found four of six evals scoring
identically in both arms, and three places where the *baseline* gave better guidance than this
skill's own references. Those three are now folded in:

- `checkscope` reads `RecordTime`, `TriggerModule` and `AutoRestartRecord`, and warns when a
  project records a fixed window with no trigger — correct wiring and the wrong plan. The
  templates ship exactly this way: a 60 s window, which for an hourly intermittent fault
  catches it under 2% of the time. It is a warning, never a problem; a file can be perfectly
  built and still be a lottery ticket.
- `references/recording-load.md` names the cycle that actually sets the floor. Axis data off
  the NC interface updates once per NC SAF cycle (typically 1–2 ms), so a request for 50 µs on
  those channels buys 20–40 identical samples per real update at 20–40× the bandwidth. Adds
  the drive-internal route (an AX8000 samples its own current loop at ~62.5 µs) for questions
  genuinely shorter than one fieldbus cycle, which no scope on the target can see.
- `references/data-triage.md` gains *Recovering a clipped channel*. Refusing to give a number
  for a saturated signal is the floor, not the ceiling: velocity clipped with position intact
  is recoverable by differentiating position, a clipped sine can be fitted from its unpinned
  samples, and the pinned fraction itself gives the amplitude via
  `1 − (2/π)·arcsin(C/A)`. Three routes agreeing is what makes it a reconstruction rather than
  a guess — and it must still be reported as reconstructed.

The evals' own headline is not that the skill scored 33/33 against 28/33. It is that the
fixtures are too small to test this skill's central claim: `needle-in-the-haystack` runs
against 20,000 rows, which pandas holds whole, while `SKILL.md` exists because twelve million
samples cannot be. See `evals/results-iteration-1.md`.

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
