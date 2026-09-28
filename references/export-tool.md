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

The binary also carries `svdx=`, `channel=`, `channellist=`, `start=` and `end=`, and its
window has matching Channels / Starttime / Endtime fields. None of those has been tried.

`tcscope.py ingest` calls this for you when handed a `.svdx`, writing the CSV to its cache
dir rather than beside the recording, then converts to Parquet. That
exact command line converted two real recordings first time (`evals/field-review-3e4c44d.md`),
with the tool found under the TwinCAT root in `Functions\TF3300-Scope-Server\`.

### The tool ignores the settings saved in the recording

A `.svdx` carries two export configurations: `<AutoSaveExportConfigurationString>` (its
`CSVProperties` empty in both real files seen) and `<ExportConfigurationString>` (full
`CSVProperties`). Editing either one — the separator, the decimal mark, `ContainEOF` — left
the tool's CSV unchanged, byte for byte apart from the file path it writes into line 2
(`evals/field-review-8bf9230.md`). Only `config=` changes the output. On one Dutch-locale
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
- **The `Offset` header row is the display offset**, set per display channel in Scope View.
  The values under it are raw: a flag drawn at offset 2 exported only 0 and 1. `manifest`
  shows it as `display_offset`; **never add it to the values.**

### Exporting from Scope View by hand: the settings

**Prefer `ingest` on the `.svdx`.** Without a `config=` the export tool writes the full
metadata header and one time column per group. When someone exports from Scope View instead
(*Export → CSV → Configure Properties*), the file depends on their settings. Different users
send different files for the same recording. Ask which settings they used, or read the answer
off `manifest --dump-header`. This table lists what to choose and why.

"Tool-verified" means the same real 60 s recording (2 ms + 4 ms groups) was exported through
`TC3ScopeExportTool.exe config=` once per option, and each CSV read back. Where Scope View's
own export may differ, that is said.

| Option (`CSVProperties` element) | Choose | Why, and how well it is known |
|---|---|---|
| **Header configuration** (`HeaderKonfiguration`, a bit mask) | The fullest preset (`All`, 16777215) | **Tool-verified.** `All` and `StandardBIN` (16383) keep `Data-Type`, `SymbolName` and `Port`. `Short` (1833) keeps `SymbolName`, `NetID` and `Port` but drops `Data-Type`; `Name` (1) keeps only names. All four read to the right groups; `manifest` shows `data_type: null` where the row is missing. A `Name`-only header leaves copies collapsed only on Scope's own `<name> (n)` naming (`matched_on: "name"`). **`None` (0) writes no header at all, and the reader refuses it**: nothing says where one group ends and the next begins. |
| **Timelines** (`TimelineMode`: `All`, `OnePerSampleTime`, `None`) | *For each sample time* | One time column per group, the layout the reader is built around. *All* (one per channel) matched *For each sample time* on the tool, but every group in that recording held one channel, so it proved nothing. **Never *None***: with interpolation off the tool wrote no file and still exited 0. From Scope View, *All* and *None* are **untested**. |
| **Interpolation** (`Interpolation`: `None`, `Shift`, `Stair`) | *None* or *Fill with previous value* | **From Scope View, both verified on a real 60 s export**: *None* writes the slow group on the first rows and then shorter rows; *Fill* repeats each slow sample (time `0,0,4,4…`). Both read to 30001 and 15001 samples over 60 s. **The tool ignored interpolation**: `Stair` and `Shift`, with any `TimelineMode`, gave its usual unpadded layout. *Shift value* from Scope View is **untested**. |
| **CSV separator / decimal mark** (`Seperator`: `Tab`, `Blank`, `Colon`, `Semicolon`, `Comma`; `DecimalMark`) | TAB or `;` with `,`, or `,` with `.` | **Tool-verified**: TAB/`,`, `;`/`,` and `,`/`.` read identically. **`,` for both** is refused: fields and decimals can't be told apart. **Blank and Colon** are refused by name, because the header's paths, dates and clock times contain the same character. |
| **Full Timestamp** (`FullTimeStamp`) | Off | On writes absolute FILETIME (100 ns ticks since 1601) in every time column. **Tool-verified**: same counts and duration, `start_filetime` equal to the header's `Starttime of export` tick. **The ticks are UTC**: the header's readable date and time beside them is local time (2 h ahead, CEST). |
| **Scale values before export** (`ScaleValues`) | Off | The reader treats values as raw, the same as the PLC variable. Scaled values are whatever the display was configured to show. On the tool, a recording without scaling came out unchanged. The effect on a scaled channel is **untested**. |
| **Include trigger info** (`IncludeTriggerInfos`) | Either | **Tool-verified**: a small table after the preamble, `TriggerGroup, Count, ReleaseTime, Comment`, one row per trigger release. The reader skips it: same counts, no `malformed_rows`. |
| **Marker windows** (`IncludeMarkerTables`: `None`, `All`, `Custom`) | None | `All` changed nothing on a recording with no markers. With markers, **untested**. |
| **Include EOF tag** (`ContainEOF`) | Either | **Tool-verified**: a trailing `EOF` row is skipped. |
| **Sort channels by sample time** (`SortChannels`) | Either | Changes only the column order. The reader keys on groups, not position. Its groups were already in sample-time order, so the tool's output did not change. |
| `ExcludeDoubleTimestamp` | — | No effect on the tool's output for this recording. |

Scope View's defaults for these options are **not yet recorded**. Both real recordings seen
carry TAB, decimal `,`, the `All` header, `EOF` on and every other option off in their
`<ExportConfigurationString>`, but a saved value is not necessarily the default.
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

**The reader was measured against 19 genuine export-tool CSVs**, covering both dialects, and
`tests/make_real_fixtures.py` reproduces the five layouts they use. The step *before* it has
now been observed too: the real tool converted two `.svdx` recordings first time with the
invocation above (`evals/field-review-3e4c44d.md`). What that leaves unproven is variety —
one machine, one tool version. The `;` delimiter has now been read in a real file, but one
the tool wrote through `config=`, not one a user sent (`evals/field-review-8bf9230.md`). The
reader still sniffs each file and reports what it detected — if something looks wrong,
`manifest --dump-header` shows the raw first lines, and those beat the sniffer.

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

### Trap 3: the time column

Assumed to be the column whose name contains "time", else column 0. If a recording names it
something else, `manifest` will show an implausible sample rate — that is the symptom.

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
