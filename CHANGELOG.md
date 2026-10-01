# Changelog

## Unreleased

### Added

- `newscope --theme auto`, now the default: follows the TwinCAT XAE Shell's colour theme, read
  from one `HKCU` registry value (Dark → `dark`, Light/Blue → `light`), else `dark`. The output
  reports `theme_source` (`evals/field-review-v1.0.0.md`, Part D).
- `events` reports a `standing` following error: `PosDiff` staying beyond 10% of its largest
  value for at least 1 s while the axis's `SetPos` rests. On a real axis driven onto an end
  stop it stood a tenth of the stroke short for 27 s and was reported only as two ramps
  (`evals/field-review-v1.0.0.md`, B1b).

### Changed

- `events`: on an integer state channel, a change between states the channel visits anyway is
  a `transition`, descriptive, instead of a `step`. A jump into a state entered only once (an
  abort, a fault state) stays a `step`, and so does every change on an error code (a channel
  at 0 at least 90% of the time). Rare but normal state pairs had taken 14 of 20 capped slots
  on a real recording (`evals/field-review-333b6c6.md`).

### Fixed

- `events`: 20 or more alike defects on a channel are `recurring` even when they are larger than
  the channel's median one. On a real command channel, 25 alike two-sample steps beside 32
  smaller ones were not flagged and took 5 of 20 capped slots (`evals/field-review-74dd86d.md`, §4).
- `events`: a following error decaying after the axis arrives is no longer a `standing` one. On
  a real axis parked at a software limit, the loop's 2.3 s settling tail was reported. A run that
  ends by the error easing under the floor while the setpoint still rests is now left out; one
  that lasts to the end, or drops off a plateau, is still reported. A first rule, on how much the
  error shrank inside the run, missed the real tail (`evals/field-review-633a9bf.md`, §1).
- `events`: a real channel with 16 or fewer distinct values no longer reports `clipping`; a
  filtered rate sitting at two of its six values had taken two capped slots.

- The sample-time rule is now the measured one. `SKILL.md`, `references/scope-configuration.md`
  and `newscope`'s note said Scope "snaps" a sample time to the task cycle, from one case. On a
  real target, Scope snaps when recording starts (not on load or Save), to each acquisition's own
  task cycle, rounding down, with one cycle as the minimum and no message: 7.5 ms recorded at
  4 ms on a PLC task and 6 ms on an NC task in the same file (`evals/field-review-74dd86d.md`).
  In eval iteration 5 every skill run had guessed at the sub-cycle case.
- Docs: save the recording before changing any setting (a change after Record discards it), and
  Save does not write an unchanged scope.
- `checkscope`: a sample time under 50 µs is named in a warning and left out of the load figure.
  Scope records it at one task cycle; 1 tick (100 ns) had been reported as ~20 000 000 samples/s
  (`evals/field-review-74dd86d.md`, §1).
- `events`: a setpoint turning round at its own rate (an acceleration command reversing just
  short of zero) is no longer a `spike`; a spike on a command must jump out of the motion before
  it (`evals/field-review-v1.0.0.md`, Part C).
- `tools/update-skill.ps1`: a `-Version` that does not exist says so (GitHub's 404) instead of
  "Could not reach the GitHub API" with proxy advice. Every failure prints plainly, says nothing
  was changed, and exits 1 (`evals/field-review-v1.0.0.md`).
- README: the zip install defaults to the Copilot folder, so Claude Code needs `-Target
  .claude\skills\twincat-scope`; a copy of the script saved from a browser needs `Unblock-File`.
- `newscope`: an NC axis's `Axes.<axis>.ToPlc.*` and `.FromPlc.*` members go on the axis's own
  tab. They had a tab of their own, named after the struct, with the axis's lone `ActPos` copied
  into it; two axes' members clashed into full-path titles (`evals/field-review-74dd86d.md`, §2).

## 1.0.0 — 2026-09-29

First public release. The development history before it is in git and in `evals/`.

### Building a recording

- `newscope` writes a `.tcscopex` from a template: fresh GUIDs with every display channel
  rewired to its own acquisition, one acquisition and display channel per requested symbol,
  per-channel `SYMBOL:TYPE:PORT`, Scope's own data types (NC axis fields and the
  axis's `ToPlc`/`FromPlc` members typed automatically, a struct member written on the axis
  itself named with its `ToPlc` path, anything undeclared reported as defaulted), NC `Axes.…` symbols routed to
  port 501, sample time and record window.
- Layout: one chart tab per device, one stacked band per quantity, at most eight traces per
  band, flags on 0/1, a lone parent block drawn beside what it drives. `--layout flat` for
  channels that share a scale. Dark (default) or light theme with a contrast-checked palette.
- `checkscope` validates a `.tcscopex`, or the project stored inside a `.svdx`: duplicate or
  dangling GUIDs, placeholders, NC symbols on a PLC port, IEC type names and `VOID`, size/type
  mismatches, unreadable or duplicate channel names, missing `AxisStyle`, disabled elements,
  and readability of the layout.
- `checkscope` warns on the recording plan: sample load against measured real projects, a
  fixed window with no trigger, trigger actions that do not stop a recording, ring-buffer
  mode, and Subsave triggers, which need the Scope View Professional licence.
- `checkscope --tmc` checks every PLC symbol against the compiled program's symbol table.
- `doctor`, `newscope` and `checkscope` need nothing but Python.

### Reading a recording

- `ingest` converts a `.svdx` (via `TC3ScopeExportTool.exe`) or a Scope CSV to Parquet, keeping
  each acquisition group's own time axis. Intermediate files go to a per-user cache.
- `manifest` reports channels, units, per-group sample rates, duration, gaps, duplicated
  display channels, display scaling (warning when a CSV's values may have been scaled on
  export), and whether cross-group timing in the export can be trusted.
- `stats` reports per-channel health: rails, flat stretches, quantisation, outliers.
- `events` finds steps, ramps, spikes, transitions, flatlines, holds, modulo wraps, clipping and
  threshold crossings. One excursion is one event; command channels, still axes and integer
  channels are recognised so they do not flood the result. On an integer state channel every
  change of value is its own step with its `from` and `to` state. Clean NC feedback that stands
  still while its setpoint moves is reported as frozen. The output is ranked - one-off defects,
  then defects that recur alike on a channel, then routine motion - and spread across the
  recording, with a complete summary of everything found.
- `plot` draws a min/max envelope per pixel bucket, never decimation.
- `correlate` normalises, reports the lag with its sign and which channel leads, and refuses
  channels on different clocks unless `--allow-cross-group` is given.
- `window` returns capped raw rows, one block per acquisition group.
- The CSV reader handles the TAB, `;`/`,` and `,`/`.` dialects, multi-rate groups that are
  repeat-padded or truncated, blank cells, trigger-info tables, EOF rows, FILETIME timestamps
  and exact copies of a channel. Headerless, Timelines *None*, Blank- and Colon-separated
  exports are refused by name rather than misread.

### Guidance

- `SKILL.md`: four hard rules (no safety logic, no writes to a live machine, no unverified
  claims, a human starts every recording) and the two workflows.
- `references/`: the diagnosis method, sizing a recording, the `.tcscopex` schema, and the
  export tool with its CSV traps.
- `evals/`: behaviour and trigger evals against a no-skill baseline, and write-ups of every
  field session on a real machine.

### Known gaps

- The analysis verbs have run against real recordings mostly from one machine, not the variety
  of real exports.
- A CSV exported from Scope View with *Scale values before export* on carries scaled values
  under a header identical to a raw export's, and the file does not record the option. `manifest`
  reports each channel's `scale_factor`/`scale_offset` and, for CSV input, warns that the values
  may be scaled. It cannot tell which, and with a **Name-only** header, which has no scaling rows,
  it cannot see the scaling at all. `ingest` on the `.svdx` is not affected: the export tool
  writes raw values by default (`evals/field-review-333b6c6.md`, M1).
- Untested: what a *Subsave* trigger records (it needs a Professional licence), marker tables
  in an export, an axis parked exactly at a limit, and a genuine saturation on a real machine.
- Installation through GitHub Copilot in VS Code has not been tried.
