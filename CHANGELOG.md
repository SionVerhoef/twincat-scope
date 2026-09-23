# Changelog

## Unreleased

First working version. Not yet published.

### Flags back on 0/1, and Scope View's own CSV export

Round 6 of the field test (`evals/field-review-6872161.md`).

- **Flags are drawn on 0/1 again.** Stacking them 1.5 apart by display offset was tried and
  rejected: the lanes were too close to tell which trace was high, and the axis labels no
  longer lined up with anything. Colour is what separates flags in one band.
- **Copies are collapsed in Scope View's own CSV export too.** That export has one shared
  time column and no symbol rows, so the only evidence of a copy is Scope's `<name> (n)`
  naming beside a `<name>` with identical data; `copies_collapsed` now says which evidence
  was used (`matched_on: "symbol"` or `"name"`). The docs say to prefer `ingest` on the
  `.svdx`.
- The re-read of round 5's recordings with the new reader: 40 channels, not 42, and nothing
  else lost. `ColorMode` offers Custom, First Channel or a named channel — nothing that
  follows the IDE theme.

### The whole path, run once — and a copy the export made

Round 5 of the field test (`evals/field-review-3e4c44d.md`): a generated 40-channel file
recorded, a trigger configured in Scope View was detected, and the real export tool converted
the `.svdx` with `ingest`'s command line on its first run. `BaseSampleTime` being 100 ns ticks
is confirmed a second way: Scope saved 80000 and the recording ran at 125 Hz.

- **Exported copies are read as one channel.** Scope exports a column per display channel, so
  the parent step `newscope` draws in three tabs came out three times — 42 columns for 40
  acquisitions. Exact copies (same symbol and port, same time column, same values) are
  collapsed on read, listed in `manifest` as `copies_collapsed`, and kept through Parquet.
- **`display_offset` in `manifest`.** The CSV's `Offset` header row is where a trace was drawn;
  the values under it are raw. It is reported, and never added.
- **`newscope` notes that Scope snaps the sample time** to a multiple of the task cycle —
  10 ms was saved as 8 ms on a 4 ms task.

### A sequencer's step drawn beside what it drives

From the Part A field review: a parent sequencer's step got a tab to itself, and a step is
read against the blocks it drives, not alone.

- **A block with one channel and blocks beneath it gets no tab of its own.** Its channel is
  drawn first in its band in each descendant's tab — extra display channels on one
  acquisition, so recorded once. A namespace (`GVL`, `MAIN`) or a lone block with nothing
  beneath it keeps its tab.
- **`checkscope` tells context from a slip.** One acquisition drawn in several tabs is
  counted (`acquisitions_in_several_tabs`) instead of drawing a warning; drawn twice in one
  tab, it is two identical traces on one axis and still warns.

### This version's own output, recorded

Part A of the field-test brief, run on this version's `newscope` output with no hand edits
(`evals/field-review-fe9b487.md`). Status lines throughout now say what it showed.

- **Round 3 on main's own output recorded**: five NC axis channels, dark theme, an `AxisStyle`
  on all eight axes — accepted, and matching one Scope wrote element for element but the grid
  colour.
- **The first bit, integer and PLC channels from a generated file recorded**: two NC axis
  channels on 501 and a `BOOL`, an `INT` enum and an `LREAL` on 851, across three tabs.
- **Scope draws the stored colours as written** and does not follow the IDE theme; the dark
  default read well in both.
- A 40-channel function-block recording laid out with no crowding warning and every band
  enabled. Two readability findings are open: a band of two flags is hard to read next to
  taller neighbours, and a lone step enum or flag gets a tab to itself.

### Bands that do not flatten each other, and disabled elements said out loud

A follow-up field session regenerated a 32-channel function-block recording, in a
prefix-style house, with the current version. Names were now unique, but the layout had three
faults, and an older hand-edited file had a fourth.

- **Bits and integers get separate bands.** A step enum and a counter shared the digital
  axis with seven 0/1 flags, and a step running to 200 draws every flag as a flat line. Bits
  now band as `Digital / state`; integers as `Step / count`, even when their name says
  "state".
- **"Loading" is not a load.** A length named for a loading zone matched `load` and was filed
  under torque.
- **`newscope` no longer writes a band `checkscope` calls crowded.** Past eight traces a band
  is split into even parts, so eleven flags become 6 + 5. `--layout flat` still means one
  axis.
- **`checkscope` warns about disabled acquisitions, bands and channels.** A file came back
  with every band `Enabled=false`, showing nothing until they were enabled by hand; `newscope`
  never writes `Enabled`, so it was edited afterwards. A warning, not a failure: disabling is
  a Scope View feature. `SKILL.md` now says to change a layout by regenerating.

Names such as `…TravelActual` or `…Target1` still land in `Other`: nothing in them says
position, and a guess would misfile the channels whose names mean something else.

### A generated file records, and charts styled for one background

A second field session took one generated file through three rounds on a live target. An IEC
type was read by Scope as `VOID` and refused; with `REAL64`, an axis symbol on port 851 was
"not found"; with port 501 as well, **it recorded** — the first data a generated `.tcscopex`
has produced. Both blockers were already fixed here; the session ran an older version. Its
write-up, anonymised, is `evals/field-review-1fa0e9b-rounds.md`.

- **`newscope --theme dark|light`**, dark by default. Generated charts rendered as near-white
  panels in a dark IDE, from hard-coded light greys and no axis styling at all. Every axis now
  carries an `AxisStyle` — where real projects keep one — and panels, axis text, grid and
  traces are chosen for one background. The trace palette is checked for contrast against it,
  and its first four for colour-blind separation between every pair, since a band's traces
  share one axis. No value that follows the IDE theme has been seen, and whether Scope themes
  colours a file leaves out is untested, so a file picks one. Since seen in the field: Scope
  accepted the `AxisStyle` on every axis, the file recorded, and it read well with the IDE in
  either theme (`evals/field-review-fe9b487.md`).
- **`checkscope` refuses `VOID`.** It is what Scope wrote back after failing to read `LREAL`,
  so a `VOID` means the file has been opened, misread and saved; it drew only a soft warning.
  `checkscope` also reports which `theme` a file is styled for, warns about axes with no
  `AxisStyle`, and warns when a known NC field carries a type other than the table's.
- **NC axis fields are typed from their names.** For `Axes.<axis>.<field>` on the NC port,
  `ErrorCode`, `AxisState` and the other status fields are `UINT32` and the motion values
  `REAL64` — every such acquisition in the nine files of one real project agrees, and the names
  are Beckhoff's rather than a house style. `ErrorCode` was written 8 bytes wide, and every
  axis channel was reported as a defaulted guess, which buried the defaults that matter. A
  declared type, an explicit non-NC port or a deeper path still wins.
- `INT8` and `UINT32` join the types seen in real files; the docs no longer claim an IEC type
  name is "accepted by nothing and rejected by nothing".
- **How to open a generated file:** add it to an existing TwinCAT Measurement project.
  Double-clicked, one started a new-project wizard that hung.
- Both templates are restyled for the dark default with their GUIDs unchanged, and keep
  `TargetPort` 851: their symbols are the PLC's `NcToPlc` copy of the axis, not NC symbols.

### A generated file that can actually record

A field session took a generated 53-channel project to a running machine. It opened in Scope
View, `checkscope` passed it, and it recorded nothing — every channel had the wrong type and
width, every axis channel was looked up in the wrong runtime, and every column of the export
was called `Signal`. The review is in `evals/field-review-1fa0e9b.md`.

- **The ADS port follows the symbol.** `Axes.…` is served by the NC runtime on 501, every
  other symbol by `--port`. One port across both namespaces resolves the PLC channels and
  fails the axis ones with "Symbolname could not be found", which reads as a naming problem
  and is not one.
- **`DataType` is Scope's vocabulary, not IEC's** — `BIT`, `INT16`, `REAL64`, with
  `VariableSize` to match. Declare a type per channel as `SYMBOL:BOOL`, `:INT`, `:LREAL`.
  Undeclared channels are still written as `REAL64`, but are now reported as *defaulted*
  rather than passed off as resolved. Both templates shipped `LREAL`, which appears in none
  of the seven real project files this schema was read from; they now ship `REAL64`.
- **Every channel gets its own name.** `<Name>` is the Scope tree label *and* the CSV column
  header, so the template's placeholder exported fifty-three columns called `Signal`. Names
  are derived from the symbol's leaf and lengthened along the path only where two would
  collide.
- **`--record-time <seconds>`.** The window was fixed at the template's 60 s with no way to
  change it, while the event being chased ran longer than that. `checkscope` already warned
  about the window; there is now a way to act on the warning.
- **A band decided by type where the name says nothing.** Houses that write `seStep` and
  `sbBlocked` match no quantity keyword, so a whole function block landed on one axis. Bits
  and integers now band as state.
- **`checkscope` refuses all of it**: an NC symbol on a PLC port, an IEC type name (naming the
  Scope one it means), a width that contradicts its type, and channels that would export as
  columns nobody can tell apart — and a field that is simply *absent* counts as the same
  failure as a wrong one, since an empty `DataType` says no more about how to read a variable
  than a wrong one does.
- **Bad input answers in JSON, not with a traceback**: a record window that is not a positive
  finite number of ticks, an entry with no symbol, an unrecognised type, one symbol declared
  two different ways, and a template missing a field this version needs to write — which
  would otherwise be skipped silently, leaving the template's own values in the file.
- **A port no runtime answers is caught here rather than at the machine.** `--port 85`, one
  keystroke from 851, used to pass every check and record nothing. A port outside 1–65535 is
  now refused outright, and a PLC symbol on a port below 851 — where no TwinCAT 3 PLC runtime
  listens — is reported by `newscope` and warned about by `checkscope`.
- **A channel really called `Signal` keeps its name.** The placeholder check asks whether the
  name is the symbol's own leaf, so `MAIN.fbIO.Signal` is a name rather than a template
  leftover. It also no longer hides behind the duplicate-name check, since fifty-three
  channels called `Signal` are both at once, and acquisitions with no name are all reported
  together instead of one per run.
- **`--channels ",,,"` is refused.** An entry list that names no symbol filtered to empty and
  fell through to the template's own channels, reported as `ok` — the channels someone asked
  for silently not in the file.
- **The state band follows the type table.** Which types band as state is derived from the
  table that sizes them, rather than a second list beside it, so a type added to one cannot
  go missing from the other and land on a shared axis.

`SYMBOL:TYPE:PORT` is the whole channel grammar; the port field overrides the `Axes.` rule and
reaches a second PLC runtime (852, 853…) per channel. Fields are read from the right and only
when recognisable, so a mistyped type is an error rather than part of a symbol name.

Documentation moved to `py -3`, which is how Windows invokes Python and therefore how these
commands run on a machine with TwinCAT on it; every block that uses it says what the command
is everywhere else.

### Charts laid out to be read, not just to be valid

Field feedback from a first real use of `newscope`: every requested channel arrived in a single
chart, sharing one auto-scaled axis, all in the same colour. Nothing was wrong with the file —
that is the point. A following error of a few microns next to a position of a metre is drawn
as a flat line on zero, so a correctly recorded signal is an invisible one.

- **One chart tab per device.** Taken from the symbol path with the wrapper structs stripped,
  so `MAIN.fbAxis1.NcToPlc.ActPos` groups under `fbAxis1`. Two devices whose paths end in the
  same segment keep their full paths rather than merging into one tab.
- **One stacked band per quantity inside a tab**, ordered position, following error, velocity,
  acceleration, torque/current, pressure, temperature, digital state, other. Set and actual
  position deliberately share a band — same unit, same magnitude, and the gap between them is
  the measurement. Read from the leaf name, so `PosDiff` is a following error rather than a
  position and `bPosReached` is a state rather than either. Anything unrecognised lands in a
  labelled `Other` band instead of being misfiled.
- **Channels sharing an axis get different colours**, and `StackedAxes` is set whenever a
  chart holds more than one band. `--layout flat` restores a single axis for channels that
  genuinely share a scale.
- **`checkscope` reports the layout** — charts, bands and their channels — and warns when a
  chart stacks more than six bands or a band overlays more than eight channels. Readability,
  not validity: the file is fine, the picture is not.
- **A symbol asked for twice is now recorded once**, rather than costing target bandwidth
  twice for one signal.
- `templates/axis-diagnosis.tcscopex` was regenerated in that shape: five channels, four
  bands, set and actual position together.

Still unopened in TwinCAT, so that multiple `YTChart` siblings arrive as tabs and that
`StackedAxes` is what stacks the bands remain readings of the schema rather than observations.

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

- **The analysis verbs have met one real recording of a generated file.** The whole path —
  generate, record with a trigger, convert the `.svdx`, `ingest`, `manifest` — ran once
  (`evals/field-review-3e4c44d.md`); Part B of the brief, the 19 genuine exports re-run, has
  not.
- The `;` delimiter appeared in none of the real files. It stays supported on the strength of
  the synthetic EU fixture alone.
