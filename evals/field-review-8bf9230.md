# Field review — main @ 8bf9230

Run by an agent on a Beckhoff commissioning workstation (Windows 10, Dutch locale, TwinCAT 3.1
build 4024.55, Scope 3.4.3147.18 incl. the TF3300 export tool, Python 3.12.10 under `uv` 0.12.7, Claude Code 2.1.248). The subject was the
two PRs since the last round: #26 (short rows, per-group timing, TriggerAction) and #27
(Scope View's CSV export options). The skill was reinstalled from `8bf9230` first (brief 4.0).

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; every number
is the measured one. Recordings, projects and CSVs stayed on the machine.

The material: two real 60 s `.svdx` recordings of the same shape, called **R1** and **R2**
below. Each has a 2 ms group holding one NC axis position (`REAL64`, port 501) and a 4 ms group
holding one PLC flag (`BIT`, port 851). Scope View CSV exports of R2 were already on the
machine, made in the last round: interpolation *None* and repeat-padded. There were also 20 real
`.tcscopex` projects.

## Verdict

#26 and #27 hold up on the real tool. The reader is faithful on every layout the tool wrote.
The brief's §1 pass numbers (30 001 + 15 001) came from a Scope View export whose range had
been adjusted by hand. At the default range, the tool and Scope View both give 29 999 + 15 000
(§1). There is no F1 defect. The open question in
§3 was answered, and it gave a better route than the brief planned. The tool ignores
settings saved in the recording, but takes a `config=` file. So the whole export-option matrix
ran headless on real data rather than by hand in Scope View. That matrix found two reader
defects (F2, F3). `checkscope` crashed on a `.svdx` (F4), and the test suite itself failed on
Windows (F5).

Tests: 246/246 on `8bf9230` once F5 was fixed (the 247th, `ingest_cache_checks`, is skipped
on Windows by design); 252/252 on the branch.

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
- Where the flags sit, in both the projects and the `.svdx`:

  ```
  /ScopeProject/AutoRestartRecord                                   false
  /ScopeProject/SubMember/TriggerModule/SubMember/TriggerGroup/RestartRecord   false
  /ScopeProject/SubMember/TriggerModule/SubMember/TriggerGroup/TriggerAction   NONE
  ```

  So a separate `RestartRecord` does exist, per trigger group. `AutoRestartRecord` is at
  project level in all 20 projects, and it is `false` in all 20.
- **Not done:** giving the trigger a real action in Scope View. So the real `TriggerAction`
  values and a TriggerGroup that uses one are still unknown. That needs a person at Scope View.

Found in passing: with *Include trigger info*, the tool writes a table of trigger releases.
R2 has 3 releases (at 18 648, 54 276 and 58 204) even though its action is `NONE`. So a
trigger with no action still fires and is logged.

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

### What the matrix does not answer

It is the tool's behaviour, not Scope View's. Not done, and each needs a person at Scope View:

- Scope View's defaults for each option (the brief's first row).
- That *Fill with previous value* is the option that made the repeat-padded file. The padded
  file's slow time column is `0,0,4,4…`, which fits; nobody watched it being chosen.
- *Shift value*, Timelines *All* on a group of several channels, and Timelines *None*, all
  from Scope View.
- Whether the header shows scaling on a channel that has scaling; the effect of marker windows
  on a recording that has markers.

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

### Minor, not fixed

`correlate`'s `resampled` note reads "b was linearly resampled from its own 1 axis": the
group index is printed where a word was meant.

## Remaining brief items

- **4.8 — `<Comment>` on save.** A project file on this machine carries
  `tcscope:type=default` in one acquisition's `<Comment>`, after a Scope View save: its
  layout's `LastFocused` tick matches the file's mtime. The text survived. But that
  acquisition is an **NC** channel (port 501), which the `3e4c44d` round had already
  shown. Whether Scope overwrites a hand-written comment on a **PLC** acquisition, and
  whether the text shows in the UI, are still open.
- **4.9 — parked axis.** R2's axis rests near 50 for most of the run with dither
  (quantisation step 0.000122, `pct_flat` 25.2%, p50 50.0004) and makes commanded moves up to
  221. `events`: 39, all descriptive, with 32 `ramp` on the axis and 7 `transition` on the flag.
  No `clipping`, no `flatline`, no `step`. An axis parked *at a limit* and a genuine
  saturation did not occur. Still open.
- **4.10 — does Claude Code pick the skill up unnamed?** Not tested fairly: this session was
  told the skill's name. Client: Claude Code 2.1.248, desktop app.
- **§10 — `ingest` on a large real export.** Not done. The large recordings on this machine
  belong to another project, and using them was declined. `doctor` on a machine without the
  export tool: no such machine was available.

Nothing was written to or activated on any controller. No project file was modified; the
`.svdx` edits were made on copies outside the project.
