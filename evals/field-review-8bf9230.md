# Field review — main @ 8bf9230

Run by an agent on a Beckhoff commissioning workstation (Windows 10, Dutch locale, TwinCAT 3.1
build 4024.55, Scope 3.4.3147.18 incl. the TF3300 export tool, Python 3.12.10 under `uv`
0.12.7, Claude Code 2.1.248). The subject was the two PRs since the last round: #26 (short
rows, per-group timing, TriggerAction) and #27 (Scope View's CSV export options). The skill was
reinstalled from `8bf9230` first (brief 4.0). No code was committed from the workstation; the
fixes F2-F5 travelled as a patch, and G1-G6 were fixed afterwards on a development machine.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; every number
is the measured one. Recordings, projects and CSVs stayed on the machine.

The material, all kept on the machine:

- **R1, R2.** Two real 60 s `.svdx` recordings of the same shape. Each has a 2 ms group
  holding one NC axis position (`REAL64`, port 501) and a 4 ms group holding one PLC flag
  (`BIT`, port 851). R2's axis moves (range 48.8-221); R1's stands still. Scope View CSV
  exports of R2 from the last round were also there: interpolation *None* and repeat-padded.
- **R3.** A real 600 s `.svdx` of 65.7 MB: 33 channels (10 `REAL64`, 10 `BIT`, 8 `INT16`,
  5 `UINT32`) in 5 time groups at 2, 2, 4, 4 and 12 ms, on ports 851 (three groups) and 501
  (two).
- 20 real `.tcscopex` projects.

## Verdict

#26 and #27 hold up on the real tool. The reader is faithful on every layout the tool wrote.
The brief's §1 pass numbers (30 001 + 15 001) came from a Scope View export whose range had
been adjusted by hand. At the default range, the tool and Scope View both give 29 999 + 15 000
(§1). There is no F1 defect. The open question in §3 was answered, and it gave a better route
than the brief planned. The tool ignores settings saved in the recording, but takes a
`config=` file. So the whole export-option matrix ran headless on real data, and was then
repeated for the options that matter in Scope View's own dialog. The two found two reader
defects each (F2, F3; G1, G2). `checkscope` crashed on a `.svdx` (F4) and misjudged most
trigger actions (G6), and the test suite itself failed on Windows (F5). The CLI had three
rough edges an agent actually hit (G3-G5).

Tests: 246/246 on `8bf9230` once F5 was fixed (the 247th, `ingest_cache_checks`, is skipped
on Windows by design); 252/252 with F2-F5 on Windows; 270/270 with G1-G6 on Linux.

## §1 — the original bugs, through the real tool

| | R1 | R2 |
|---|---|---|
| `ingest` wall clock | 2.9 s | 1.4 s |
| 2 ms group: `n_samples`, `t_last` | 29 999, 59.996 s | 29 999, 59.996 s |
| 4 ms group: `n_samples`, `t_last` | 15 000, 59.996 s | 15 000, 59.996 s |
| `cross_group_timing_valid`, `max_skew_ms` | true, 0.0 | true, 0.0 |
| `malformed_rows` | none | none |
| `intermediate_csv` | cache dir | cache dir |
| New files on the Desktop | none | none |
| `correlate --allow-cross-group` | `ok`, lag 16 250 samples | `ok`, lag −2 901 samples (−5.802 s) |

The tool's CSV is 24 header lines, 29 999 data rows and `EOF`. The reader reads every row.
Without `--allow-cross-group`, `correlate` refuses the pair, as it should.

### Why 29 999 and not 30 001: the export range, not the tool

R2's tool export was aligned value by value against two Scope View exports:

| Export | Range | 2 ms group | 4 ms group | Against the tool |
|---|---|---|---|---|
| Tool | …53.809 - …53.807 | 29 999, 0-59.996 s | 15 000, 0-59.996 s | — |
| Scope View, default range | …53.809 - …53.807 | 29 999, 0-59.996 s | 15 000, 0-59.996 s | **identical at zero offset**, every value |
| Scope View, range adjusted by hand (earlier round) | …53.805 - …53.805 | 30 001, 0-60 s | 15 001, 0-60 s | tool = this one from its 3rd / 2nd sample |

Scope View's dialog proposes a range that starts 4 ms after the first recorded sample, and the
tool uses the same range. The user had trimmed the earlier export's range by hand. `correlate`
gives the same lag on every route (−2 901 samples, correlation 0.2733). Recorded in
`references/export-tool.md`: compare counts only between exports with the same range.

## §2 — trigger

- `checkscope` on the two projects with a trigger whose `TriggerAction` is `NONE`:
  `trigger_configured: true`, `trigger_action: "NONE"`, `fixed_window: true`, and the
  fixed-window warning is shown. **Pass.** After F4, the same result on the `.svdx` itself.
- **`NONE` is how Scope stores the dropdown's *Set Mark*.** The dropdown and the enum behind
  it (`TwinCAT.Scope2.Communications.TriggerEventAction`, read from the installed assembly's
  public types) list the same actions in the same order. Four were set in Scope View, saved
  and read back:

  | Scope View | Written | Value | Set and saved |
  |---|---|---|---|
  | Set Mark | `NONE` | 0 | yes |
  | Start Record | `START_RECORD` | 1 | yes |
  | Stop Record | `STOP_RECORD` | 2 | yes |
  | Stop Display | `STOP_DISPLAY` | 3 | |
  | Restart Display | `RESTART_DISPLAY` | 4 | |
  | Start Subsave | `START_SUBSAVE` | 5 | |
  | Stop Subsave | `STOP_SUBSAVE` | 6 | |
  | Export | `EXPORT` | 7 | |
  | Reporting Trigger | `REPORT_TRIGGER` | 8 | yes |
  | Reporting Collector | `REPORT_DATA` | 9 | |
  | Reporting Collector + Trigger | `REPORT_DATA_TRIGGER` | 10 | |

  `checkscope` reported each saved value as written. With `START_RECORD`, `STOP_RECORD` or
  `REPORT_TRIGGER` it gave no fixed-window warning — right for the first two, wrong for the
  third (G6).
- Where the flags sit, in both the projects and the `.svdx`:

  ```
  /ScopeProject/AutoRestartRecord                                   false
  /ScopeProject/SubMember/TriggerModule/SubMember/TriggerGroup/RestartRecord   false
  /ScopeProject/SubMember/TriggerModule/SubMember/TriggerGroup/TriggerAction   NONE
  ```

  `AutoRestartRecord` is project level, and `false` in all 20 projects. `RestartRecord` is a
  separate element per trigger group, with **no property in the UI**.
- **Pre- and post-trigger.** `PretriggerTime` and `PosttriggerTime` are 100 ns ticks. The UI
  field reads `days:hours:minutes:seconds`: `00:00:05:00` saved 3 000 000 000 (5 min) and
  `00:00:00:05` saved 50 000 000 (5 s). The rows appear in the UI only for *Stop Record*.
  The *Use Pre-/Post-Trigger* switches are not written while they are on.
- **A hidden pre-trigger keeps its value.** Switched from *Stop Record* to *Set Mark*, the file
  still said `PretriggerTime 50000000`.
- A 5 min pre-trigger on a 60 s record window drew no complaint from Scope, nor from
  `checkscope` (now warned about, G6).
- A TriggerGroup, as saved with *Start Record* (values as written; the channel condition left
  out): `AutoDeleteCapacity 0`, `AutoDeleteMode Disabled`, `AutoDeleteOlderThan 0`,
  `Category None`, `ClearChart false`, `DisplayColor Highlight`, `Enabled true`,
  `ExportConfigurationString`, `ExportFileNameMask`,
  `ExportPath $ScopeProject$\Trigger Group Export`, `ExportTimeMode SinceLastTrigger`,
  `ImageSize 0`, `IncludeMarkerWindow false`, `IncludeTriggerWindow false`, `IsReleased true`,
  `IsSilent false`, `KeepPeviousExports false` (sic), `PosttriggerTime 0`, `PretriggerTime 0`,
  `ReleaseInfoCapacity 20`, `ReportChartBackground Light`, `ReportingTimeMode TimeRange`,
  `ReportingTimeRange 100000000`, `RestartRecord false`, `SeparateDirectoryPerExport true`,
  `TriggerAction START_RECORD`, and a `ChannelTriggerSet` with `CombineOption AND` and
  `ReleaseOption RisingEdge`.

Found in passing: with *Include trigger info*, the tool writes a table of trigger releases.
R2 has 3 releases (at 18 648, 54 276 and 58 204) even though its action is *Set Mark*. So a
trigger that records nothing still fires and is logged.

## §3 — export options

### Does the tool follow settings saved in the recording? **No.**

A `.svdx` is the samples in binary, then the whole project as UTF-8 XML at the end. It carries
two export configurations. `<AutoSaveExportConfigurationString>` has an empty `CSVProperties`.
`<ExportConfigurationString>` has a full one: `Seperator Tab`, `DecimalMark ,`,
`HeaderKonfiguration 16777215`, `ContainEOF True`, everything else off. Copies of R2 were
edited, and the separator, decimal mark and `ContainEOF` were changed in each element in turn.
**Every export stayed byte-identical to the unedited one**, apart from line 2, where the tool
writes the output's own path.

### What does? **`config=`**

Run with no arguments, the tool opens its window, which shows a *Config* field. The
binary's strings list the arguments `svd=`, `svdx=`, `target=`, `config=`, `channel=`,
`channellist=`, `start=`, `end=` and `silent`. `config=<file>.xml`, with root
`<ExportConfiguration>` and `Format_Properties/CSVProperties` inside, **does change the
output**. The option names and enum values were read from the installed export assembly's
public types:

| Element | Values |
|---|---|
| `Seperator`, `ArraySeperator` | `Tab`, `Blank`, `Colon`, `Semicolon`, `Comma` |
| `TimelineMode` | `All`, `OnePerSampleTime`, `None` |
| `Interpolation` | `None`, `Shift`, `Stair` |
| `HeaderKonfiguration` | bit mask; presets `None` 0, `Name` 1, `Short` 1833, `StandardBIN` 16383, `All` 16777215 |
| `IncludeMarkerTables` | `None`, `All`, `Custom` |
| booleans | `ExcludeDoubleTimestamp`, `SortChannels`, `ContainEOF`, `IncludeTriggerInfos`, `FullTimeStamp`, `ScaleValues`, `MarkerTableOnly…` |

### The matrix — R2, one option changed from the tool's defaults at a time

"Lines differ" is against the default export, with line 2 (the output path) left out.

| Option | Lines differ | Reader result |
|---|---|---|
| defaults | — | TAB, `,`; 29 999 / 15 000, `t_last` 59.996 / 59.996; no `malformed_rows`; types `REAL64`, `BIT`; ports 501, 851 |
| Interpolation `Stair` | 0 | same |
| Interpolation `Shift` | 0 | same |
| Timelines `All` | 0 | same (each group holds one channel, so this proves nothing) |
| Timelines `None` | **no file written, exit 0** | — |
| Timelines `None` + `Stair` / `Shift` | 0 | same |
| Full Timestamp | 59 998 | same counts and 59.996 s; `start_filetime` 134347139938090000 |
| Include trigger info | 5 (inserted) | same; the 5-line table is skipped, no `malformed_rows` |
| Marker tables `All` | 0 | same (the recording has no markers) |
| Scale values | 0 | same (no channel is scaled) |
| Sort channels | 0 | same (already in sample-time order) |
| Exclude double timestamp | 0 | same |
| No EOF | 1 | same |
| Header `StandardBIN` | 3 | same, types and ports kept |
| Header `Short` | 11 | same groups; `data_type: null` (no `Data-Type` row); ports kept |
| Header `Name` | 16 | same groups; `data_type: null` |
| Header `None` | 24 (no header at all) | **F2**: was one 30 s group of 3 channels, 14 999 `malformed_rows`, `ok: true`. Now refused |
| `;` with `,` | every line | same. **The first real `;` file** (written by the tool, not by a user) |
| `,` with `.` | every line | same |
| `,` with `,` | every line | refused, with the re-export hint. **Pass** |
| Blank with `,` | every line | **F3**: refused as "no numeric rows". Now refused by name |
| Colon with `,` | every line | **F3**: same. Now refused by name |

**Full Timestamp.** `start_filetime` equals the header's `Starttime of export` tick exactly.
134347139938090000 decodes to 08:59:53.809 **UTC**. The header prints it beside that as
10:59:53.809, which is local time (CEST). So the ticks are UTC.

**Interpolation is ignored by the tool** in every combination tried. **Timelines `None` with
interpolation `None` writes nothing and exits 0**: a script would find no file and no error.

### Scope View's own dialog

The matrix above is the tool's behaviour. The options that matter were then exported from
Scope View by hand, on R2, at the dialog's default range.

**Scope View's defaults**, the dialog untouched:

| Option | Default |
|---|---|
| Sort by sample time | on |
| Scale, EOF tag, Full Timestamp, Trigger infos | off |
| Timelines | For each sample time |
| Interpolation | None |
| Separator / decimal | Comma / Point |
| Header | **Name only** |
| Marker windows | None; "only included channels/marker" on |

So Scope View's defaults *are* the `,`/`.` Name-only dialect of the 19 earlier exports; the
TAB/`,` full-header dialect is the tool's, on a Dutch locale. **The dialog remembers the last
settings used**: a later export came out TAB-separated although Comma is the default.

| Option | Tool | Scope View |
|---|---|---|
| Defaults | TAB/`,`, full header; 29 999 / 15 000; types and ports | `,`/`.`, Name only; 29 999 / 15 000; `data_type: null` |
| Fill with previous value (`Stair`) | ignored, output unchanged | slow group padded, `repeat_factor` 2. **Confirmed: this is the padding option** |
| Shift value | ignored | reads 29 999 / 15 000. Slow values sit only on rows whose time matches; the rows between hold single-space cells (`2,50, , `) |
| Timelines All | unchanged (one channel per group, so proves nothing) | same as the tool |
| Timelines None | no file written, exit 0 | **G2**: no time column at all. Read with a value as the time (`t_first` 0.050 > `t_last` 0.0499, 14 999 malformed) and `ok: true`. Now refused |
| Header Full | read | read, same symbols, types, ports and rates. **Pass** |
| Header None | refused (F2) | refused (F2) on a real Scope View file; with trigger info on, read as one 30 s group of 3 channels, `ok: true` (**G1**). Now refused |
| `;` with `,` | read | read. **The first `;` file a user exported** |
| Trigger info | table skipped, no malformed rows | same |

Not tried from Scope View: Full Timestamp, Timelines None with interpolation, Blank and Colon.
Still untested anywhere: whether the header shows scaling on a scaled channel, marker windows
on a recording that has markers, and Timelines *All* on a group of several channels.

## Findings, and what was done

### F2 — a headerless export was read as one group, `ok: true`

Header preset `None` writes data rows and `EOF`, nothing else. `sniff_csv` found no
metadata, so `_flat_group` took column 0 as the time column and every other column as a
channel. That included the 4 ms group's own clock. The 4 ms group's short rows became
14 999 `malformed_rows`. **Done:** with no header row and more than two columns the file is
refused, since nothing says where one group ends. A two-column headerless file is still read.
Regression check: `export_option_checks`, built on the real two-rate fixture.

### F3 — Blank and Colon separators sent the user to the wrong setting

Both are real options. Header lines contain spaces and `:` (the path, `10:59:53.809`), so
neither can be read safely. **Done:** `_unsupported_separator` spots data rows split cleanly
by either, before the delimiter vote, and the refusal names it and lists what works. Two
regression checks.

### F4 — `checkscope` on a `.svdx` died in a traceback

`read_tcscopex` decoded the whole file as UTF-8. **Done:** if the file does not start with
XML, the last `<?xml` holding a `<ScopeProject>` is parsed. A file with no project is refused
in JSON. On R1 and R2 it now reports the trigger as above. Two regression checks, built on a
synthetic `.svdx`: binary bytes, then the template's XML.

### F5 — the suite failed on Windows

`Path.write_text` translates `\n`, so the fixture generators' `"\r\n".join(...)` wrote
`\r\r\n`. `splitlines()` then saw a blank line after every line, and `data_line` pointed into
the header. Result: 2 FAILs (`a row cut off mid-group is counted as malformed`, `a small file
ending in short rows keeps its full width`), then a `ValueError` crash in `cut_mid_row`.
The handoff's 247/247 was presumably measured on Linux. **Done:** `newline=""` on every CSV write in the
generators and tests, and a check that no generated fixture contains `\r\r\n`.

### G1 — a trigger-info table stood in for a missing header

F2's refusal keyed on "no line above the data". A headerless Scope View export with *Include
trigger info* has the release table there, so it was read as one 30 s group of 3 channels,
`ok: true`. **Done:** the table (from its `TriggerGroup` row on) no longer counts as a header,
nor as a source of channel names. Regression checks: the headerless file with the table is
refused, and a full-header file with the table still reads as two groups.

### G2 — Timelines *None* has no time column, and a value was read as one

Scope View's *Timelines None* writes the values only. The reader took the first value column
as time and reported `ok: true` with `t_last` before `t_first`. **Done:** a group whose time
column ever runs backwards is refused, and the fix names Timelines. A time column never runs
backwards; a signal nearly always does. Regression check on the two-rate fixture with its
time columns removed.

### G3 — `ingest` had no default output

In 4.10 the agent's first `ingest` left out `-o` and got an argparse error. **Done:** `-o` is
optional. Without it the Parquet goes to the cache dir, as `<stem>-<hash of the input
path>.parquet`, and `output` names it. The hash matters: Scope's default file names repeat from
project to project, and the stem alone would let one recording overwrite another's cache.

### G4 — argument errors were the one answer that was not JSON

A missing argument, an unknown verb or an unknown flag printed argparse's text on stderr.
**Done:** they come back as `{"ok": false, "error": ..., "fix": <usage>}`, still exit 2.

### G5 — `ingest` and `manifest` disagreed on "groups"

On R3, `ingest` said `groups: 33` and `manifest` listed 5. Both were right about different
things: R3 was exported per display channel, one time column per channel, and `manifest`
merges twins into one entry. **Done:** `ingest` now calls its count `time_columns`.

### G6 — `checkscope` took every action but *Set Mark* for a triggered recording

Only an action that starts, stops or sub-saves the recording changes what is kept. Display,
export and reporting actions fire and are logged, and the window stays fixed, but the warning
was dropped for all of them. **Done:** the fixed-window warning now stands unless an action is
*Start/Stop Record* or *Start/Stop Subsave* (the Subsave pair inferred from its name, not
observed). The warning names the action as Scope View does (`NONE (Set Mark)`). Every trigger
group is reported in `trigger_groups` with its pre- and post-trigger in seconds, whatever the
action, because a hidden pre-trigger persists. A pre-trigger longer than the record window is
warned about. An action outside the enum is reported and not judged.

### Minor — fixed

`correlate`'s `resampled` note read "b was linearly resampled from its own 1 axis": the group
index was printed where a word was meant. It now names both groups.

## Remaining brief items

- **4.8 — `<Comment>` on save: answered for PLC.** Scope had filled a PLC acquisition's
  `<Comment>` with the variable's declaration comment (85 characters). A hand-written
  `tcscope:type=default` replaced it and **survived save, close and reopen**; `checkscope`
  stays ok. The UI shows the field only as *Symbol Comment* in the DataPool acquisition's
  properties — not in the chart, legend or tooltip. **Caution:** on a PLC channel, a marker
  written there overwrites the declaration comment. Whether the CSV's `SymbolComment` row
  then carries the marker is not verified.
- **4.9 — parked axis.** R2's axis rests near 50 with dither (quantisation step 0.000122,
  `pct_flat` 25.2%, p50 50.0004) and makes moves up to 221. `events`: 39, with 32 `ramp` on the
  axis and 7 `transition` on the flag. No `clipping`, `flatline` or `step`. An axis parked
  *at a limit* and a genuine saturation did not occur. **Still open.**
- **4.10 — does the skill get picked up unnamed? Pass**, on the Claude desktop app 2.7032.0,
  Code tab. Asked "why did the axis fault" in a folder holding a `.svdx`, the agent loaded the
  skill by itself and followed the ladder. It said correctly that the recording holds no fault
  and listed what was not recorded, proposed a triggered re-recording, and left *Record* to
  the user. Two faults: its first `ingest` left out `-o` (G3, G4), and it offered example NC
  error IDs that came from neither the skill nor the recording. `SKILL.md` now says to quote
  an error code only from the recording or a named source.
- **§10 — `ingest` on a large real export (R3).**

  | Step | Wall clock | Peak RSS |
  |---|---|---|
  | `ingest` .svdx → Parquet, in total | 16.7 s | — |
  | of which the export tool | 6.8 s | 58 MB |
  | `ingest` from the CSV | 9.8 s | 533 MB |
  | `manifest` / `stats` / `events` on Parquet | 1.2 / 1.2 / 1.3 s | 500 / 528 / 531 MB |
  | `manifest` / `stats` on the CSV | 8.9 / 9.1 s | 361 / 329 MB |

  Sizes: `.svdx` 65.7 MB, CSV 101.1 MB, Parquet 39.6 MB. 300 003 rows; the two 2 ms groups
  hold 300 003 and 299 996 samples, the 4 ms groups 150 002 and 149 999, the 12 ms group
  50 002. `max_skew_ms` 18.0, inside the 20 ms limit. 3 copies collapsed, no malformed rows.
  **Parquet verbs are ~7× faster but peak higher (~500 MB) than the CSV path (~330-360 MB)**,
  which the "ingest once, then everything is cheap" framing does not mention.

  `events` found 13 882: ramp 4 376, step 3 575, spike 2 246, flatline 1 990, transition
  1 690, clipping 5; per channel from 2 447 down to 5. Whether that is real machine activity
  or over-firing needs someone to look at the busiest channel's events, the flatlines and
  steps first. **Open.**
- **`doctor` on a PC with no TwinCAT: pass.** Under a bare Python, `ok: false`, with uv and
  numpy/pyarrow/matplotlib each missing and each given a fix. After installing uv,
  `uv run … doctor` gives `ok: true`, with only the export-tool check failing and the note that
  CSV and Parquet still work. `uv run` installed 12 packages in 321 ms.

Still untested: the tool's `channel=`, `channellist=`, `start=` and `end=` arguments.

Nothing was written to or activated on any controller. No project file was modified except
scratch copies; the `.svdx` edits were made on copies outside the project.
