# Getting data out — the export tool and the CSV traps

## `TC3ScopeExportTool.exe`

Ships with TE130x Scope View and TF3300 Scope Server, and **runs without Visual Studio** —
which is what makes headless analysis possible at all.

```
TC3ScopeExportTool.exe "svd=C:\path\rec.svdx" target=C:\path\out.csv silent
```

| Parameter | Meaning |
|---|---|
| `svd=` | Input `.svdx` (or legacy `.svd`). Quote it — Beckhoff paths contain spaces. |
| `target=` | Output file; the extension selects the format. |
| `silent` | No UI. Required for scripting. **Without it — or with no arguments at all — the tool opens a window and waits**, which hangs a script. |
| `config=` | An `.xml` export configuration, root `<ExportConfiguration>`, CSV options under `Format_Properties/CSVProperties`. **Verified:** it changes the output. The options, and their element names, are in the settings table below. |
| `channel=`, `channellist=` | Export only the named channels, by display name (`channel=ActPos`). **Verified.** `channellist=` separates names with **`;`** (`channellist=ActPos;SetPos;PosDiff`). **A wrong separator fails silently, exit 0:** `,` or `\|` is ignored and every channel is exported, and names separated by spaces write **no file at all**. `channel=` given twice keeps only the last. So check which columns came out, and that a file did. |
| `start=`, `end=` | The export range, **as absolute FILETIME ticks** (UTC, 100 ns since 1601), the same numbers the CSV header prints as `Starttime of export`. **Verified:** a 10 s range gave 5 001 + 2 501 samples (2 ms + 4 ms groups), so both ends are included. **Milliseconds, a date or a clock time are ignored without a word** — exit 0, full range — so check the header of what came out. |

The binary also carries `svdx=`, and its window has matching Channels / Starttime / Endtime
fields. **Verified:** `svdx=` is an alias of `svd=`.

`tcscope.py ingest` calls this for you when handed a `.svdx`, writing the CSV to its cache
dir rather than beside the recording, then converts to Parquet. That exact command line has
converted real recordings, with the tool found under the TwinCAT root in
`Functions\TF3300-Scope-Server\`. Once, on a large recording, the tool exited 0, wrote no CSV
and left an empty directory named after the target; the same command again worked. So `ingest`
tries once more when no file appears, removes that empty directory, and refuses only after the
second empty run.

### The tool ignores the settings saved in the recording

A `.svdx` carries two export configurations: `<AutoSaveExportConfigurationString>` (its
`CSVProperties` empty in both real files seen) and `<ExportConfigurationString>` (full
`CSVProperties`). Editing either one — the separator, the decimal mark, `ContainEOF` — left
the tool's CSV unchanged, byte for byte apart from the file path it writes into line 2. Only
`config=` changes the output. On one decimal-comma-locale
workstation, with no `config=`, the tool wrote TAB, decimal `,`, the full header and a
trailing `EOF`.

### The export range decides the sample count

The tool and Scope View export the same samples when they use the same range. On a real 60 s
recording (a 2 ms group and a 4 ms group), Scope View's export dialog proposed a range starting
4 ms after the first recorded sample. The tool used that same range. Both exports held
29 999 + 15 000 samples over 0-59.996 s, with the same start and end ticks, and every value
matched. An earlier Scope View export of the same recording, whose range had been adjusted by
hand, held 30 001 + 15 001 over 0-60 s. So **compare sample counts only between exports with
the same range**, and read the range from the header's `Starttime of export` and
`Endtime of export`.

### Two things the export does that the recording did not

- **One column per display channel, not per acquisition.** A channel drawn in three tabs
  exports three times — `<name>`, `<name> (1)`, `<name> (2)`, each in a group of its own. The
  reader collapses exact copies (same symbol and port, same time column, same values) and
  `manifest` reports them as `copies_collapsed`, with `matched_on: "symbol"`. The same symbol
  recorded at another rate is a second recording and stays.
- **The `Offset` header row is the channel's scaling offset**, beside `ScaleFactor`, set per
  display channel in Scope View. With *Scale values before export* off, the values under it
  are raw: a flag drawn at offset 2 exported only 0 and 1, and an axis given factor 2 and
  offset 10 exported its plain position. `manifest` reports it as `scale_offset` and warns;
  give both readings until the export setting is known.
- **Scope View's CSV can carry one leading sample more** than `ingest` of the same `.svdx`:
  5 101 rows against 5 100, with CSV row *i* equal to `.svdx` row *i − 1*. When comparing
  the two, align on the values or the time column, never on the row number.

### Exporting from Scope View by hand: the settings

**Prefer `ingest` on the `.svdx`.** Without a `config=` the export tool writes the full
metadata header and one time column per group. When someone exports from Scope View instead
(*Export → CSV → Configure Properties*), the file depends on their settings. Different users
send different files for the same recording. Ask which settings they used, or read the answer
off `manifest --dump-header`. This table lists what to choose and why.

"Tool-verified" means the same real 60 s recording (2 ms + 4 ms groups) was exported through
`TC3ScopeExportTool.exe config=` once per option, and each CSV read back. "SV-verified" means
the same recording was exported from Scope View's own dialog with that option and read back.
The *Scope View default* column is what the dialog offered untouched on one workstation
(Scope 3.4). **The dialog then remembers the last settings used**, so the next export from
that PC is not the default: one came out TAB-separated while the default is Comma. Always
check the file, not the user's memory of the dialog.

| Option (`CSVProperties` element) | Scope View default | Choose | Why, and how well it is known |
|---|---|---|---|
| **Header configuration** (`HeaderKonfiguration`, a bit mask) | **Name only** | ***Full*** (`All`, 16777215) — **change it**, the default is too thin | **Tool- and SV-verified.** `All` and `StandardBIN` (16383) keep `Data-Type`, `SymbolName` and `Port`. `Short` (1833) keeps `SymbolName`, `NetID` and `Port` but drops `Data-Type`; `Name` (1) keeps only names. All four read to the right groups; `manifest` shows `data_type: null` where the row is missing. A `Name`-only header leaves copies collapsed only on Scope's own `<name> (n)` naming (`matched_on: "name"`). **`None` (0) writes no header at all, and the reader refuses it**, with or without a trigger-info table above the data: nothing says where one group ends and the next begins. |
| **Timelines** (`TimelineMode`: `All`, `OnePerSampleTime`, `None`) | For each sample time | *For each sample time* | One time column per group, the layout the reader is built around. *All* (one per channel) matched *For each sample time* on the tool and in Scope View, but every group in that recording held one channel, so it proved nothing. **Never *None***: from Scope View it writes no time column at all, and the reader refuses a time column that runs backwards; the tool, with interpolation off, wrote no file and still exited 0. |
| **Interpolation** (`Interpolation`: `None`, `Shift`, `Stair`) | None | *None* or *Fill with previous value* | **SV-verified, all three.** *None* writes the slow group on the first rows and then shorter rows. *Fill with previous value* (`Stair`) repeats each slow sample (time `0,0,4,4…`, `repeat_factor` 2). *Shift value* puts each slow value only on the row whose time matches and leaves single-space cells between (`2,50, , `); it read to 29 999 + 15 000, the same as the tool at that range. **The tool ignores interpolation**: `Stair` and `Shift`, with any `TimelineMode`, gave its usual unpadded layout. |
| **CSV separator / decimal mark** (`Seperator`: `Tab`, `Blank`, `Colon`, `Semicolon`, `Comma`; `DecimalMark`) | Comma / Point | TAB or `;` with `,`, or `,` with `.` | **Tool-verified**: TAB/`,`, `;`/`,` and `,`/`.` read identically; **SV-verified** for `;`/`,` and the `,`/`.` default. **`,` for both** is refused: fields and decimals can't be told apart. **Blank and Colon** are refused by name, because the header's paths, dates and clock times contain the same character. |
| **Full Timestamp** (`FullTimeStamp`) | Off | Off | On writes absolute FILETIME (100 ns ticks since 1601) in every time column. **Tool-verified**: same counts and duration, `start_filetime` equal to the header's `Starttime of export` tick. **The ticks are UTC**: the header's readable date and time beside them is local time (2 h ahead, CEST). |
| **Scale values before export** (`ScaleValues`) | Off | Off | **Field-verified on a scaled channel** (factor 2, offset 10). On, the values are factor × raw + offset (an offset alone is applied too, and a scaled integer stays whole). Off, they are raw. **The header is identical either way**: the `ScaleFactor` and `Offset` rows show the channel's scaling, not whether it was applied. So `manifest` reports `scale_factor`/`scale_offset` and, for a CSV, warns that the values *may* be scaled. **Report both readings** — the value as it stands, and factor × value + offset — until the export setting is known. Do not take raw for the real quantity: Scope View charts the channel scaled, a scaling is often the conversion to the unit the reader means (a drive's torque word to percent), and the file does not say which of the two that is. In evals iteration 6 every run that read raw as real gave one confident number where the two readings straddled the limit being asked about. The export tool writes raw unless `config=` says `ScaleValues` True, so `ingest` on the `.svdx` does not warn. A **Name-only** header carries no scaling rows, so a scaled export with it cannot be detected at all: one more reason for the Full header. |
| **Include trigger info** (`IncludeTriggerInfos`) | Off | Either | **Tool- and SV-verified**: a small table, `TriggerGroup, Count, ReleaseTime, Comment`, one row per trigger release. The reader skips it: same counts, no `malformed_rows`. |
| **Marker windows** (`IncludeMarkerTables`: `None`, `All`, `Custom`) | None ("only included channels/marker" on) | None | `All` changed nothing on a recording with no markers. With markers, **untested**. |
| **Include EOF tag** (`ContainEOF`) | Off | Either | **Tool-verified**: a trailing `EOF` row is skipped. |
| **Sort channels by sample time** (`SortChannels`) | On | Either | Changes only the column order. The reader keys on groups, not position. Its groups were already in sample-time order, so the tool's output did not change. |
| `ExcludeDoubleTimestamp` | — | — | No effect on the tool's output for this recording. |

So Scope View's defaults give the `,`/`.` dialect with a Name-only header, and the tool (on a
decimal-comma-locale PC) gives TAB/`,` with the full header. Both read; only the second says which
symbol, type and port each column is. The one change worth asking a user for is the header.
Report any other layout with `manifest --dump-header`, redacted per `examples/README.md`.

### Formats and licensing

| Format | Licence |
|---|---|
| `csv` | No additional licence |
| `svb` | No additional licence |
| `tdms`, `dat` | **Require a full View or Server licence** |

Default to CSV. A pipeline built on TDMS fails on exactly the machines least able to fix it.

### Finding it

Do not hardcode the path — it moves between TwinCAT versions and between TE1300 and TF3300
installations. `tcscope.py doctor` searches the usual roots, honours `TCSCOPE_EXPORT_TOOL`,
and caches what it finds. If discovery fails:

```powershell
$env:TCSCOPE_EXPORT_TOOL = "C:\TwinCAT\Functions\TE1300-Scope-View\TC3ScopeExportTool.exe"
```

## The CSV traps

**The reader was measured against 19 genuine export-tool CSVs** and Scope View's own exports,
covering the TAB, `;` and `,` dialects; `tests/make_real_fixtures.py` reproduces their
layouts. What is unproven is variety — one machine, one tool version. The reader sniffs each
file and reports what it detected; if something looks wrong, `manifest --dump-header` shows
the raw first lines, and those beat the sniffer.

### Trap 1: the European locale

On a Dutch or German Windows, Beckhoff tooling exports **`;` as the field delimiter and `,`
as the decimal separator**:

```
Time;Axis1.ActPos;Axis1.ActVelo
0,000000;0,009522;8,000000
```

A reader that assumes `,` delimits fields sees one column of nonsense — or worse, parses
`1,5` as `15` and returns a plausible number that is wrong by an order of magnitude. That is
the failure mode to fear: not a crash, a quiet tenfold error in a torque reading.

`sniff_csv()` picks the delimiter by consistency of field count across sample lines, then
infers the decimal separator from it. `manifest` reports both — **check them once** on any
new export source before trusting the numbers.

### Trap 2: the preamble

The export writes name/value metadata lines before the header row, and a blank line between.
Row indices into a blank-filtered list do not match indices into the raw file, and getting
this wrong silently parses the header row as data — producing one row of `NaN` and a
duration of `NaN`. The reader tracks raw indices for this reason.

### Trap 3: the time columns

There is one time column per acquisition group, not one per file, and each channel is
timestamped from its own group's column. The reader finds them from the header's group layout.
An export with no time column (Timelines *None*) is refused, because a value column read as
time runs backwards; an implausible `sample_time_ms` in `manifest` is the symptom of anything
else going wrong here.

### Trap 4: size

CSV is the slow path; it is text, and parsing 12M samples takes real time. `ingest` to
Parquet once and everything afterwards is fast. Do not re-read the CSV for each question.

## Contributing a real export

The format questions are settled. What is still worth having is a recording of a *known
fault*, which is what turns generic advice into a worked example. Values can be redacted
freely — only the shape matters.

It belongs in `examples/`, not `tests/fixtures/`: the fixtures there are generated by
`tests/make_real_fixtures.py` and gitignored, and `examples/README.md` carries the redaction
checklist a real recording has to pass. Read that first — recordings carry more identifying
detail than people expect.
