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
| `silent` | No UI. Required for scripting. |

`tcscope.py ingest` calls this for you when handed a `.svdx`, writing the CSV to its cache
dir rather than beside the recording, then converts to Parquet. That
exact command line converted two real recordings first time (`evals/field-review-3e4c44d.md`),
with the tool found under the TwinCAT root in `Functions\TF3300-Scope-Server\`.

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

**Prefer `ingest` on the `.svdx`.** The export tool offers no choices to get wrong, and it
writes the full metadata header. When someone exports from Scope View instead
(*Export → CSV → Configure Properties*), the file depends on their settings. Different users
send different files for the same recording. Ask which settings they used, or read the answer
off `manifest --dump-header`. This table lists what to choose and why.

| Option | Choose | Why, and how well it is known |
|---|---|---|
| **Header configuration** | The fullest preset: `SymbolName`, `Data-Type`, `Port`, `SampleTime[ms]`, `Offset` rows | A `Name`-only header, as seen in the field, leaves the reader unable to tell which symbol a column is, what type it was, or where it was drawn. Copies are then collapsed only on Scope's own `<name> (n)` naming (`matched_on: "name"`). |
| **Timelines** | *For each sample time* | One time column per group, the layout the reader is built around. *All* (one per channel) should read as one-channel groups, but that is **untested**. **Never *None***: the reader then takes the first value column for time and reports nonsense. |
| **Interpolation** | *None* or *Fill with previous value* | **Both verified on a real 60 s export** (2 ms + 4 ms groups): *None* writes the slow group on the first rows and then shorter rows, and *Fill* repeats each slow sample (time `0,0,4,4…`). Both read to 30001 and 15001 samples over 60 s. *Shift value* is **untested**. |
| **CSV separator / decimal mark** | TAB or `;` with `,`, or `,` with `.` | The sniffer reports what it found. **Never `,` for both**: fields and decimals can't be told apart, so the reader refuses the file. |
| **Full Timestamp** | Off | On writes absolute FILETIME (100 ns ticks since 1601). The reader converts it to time since the first sample and reports `start_filetime`. **Tested on a derived file, not yet a real one.** |
| **Scale values before export** | Off | The reader treats values as raw, the same as the PLC variable. Scaled values are whatever the display was configured to show. |
| **Include trigger info**, **Marker windows** | Off / none | Extra rows or tables in the file. **Untested**: they may be counted as `malformed_rows`. |
| **Include EOF tag** | Either | A trailing `EOF` row is skipped. |
| **Sort channels by sample time** | Either | Changes only the column order. The reader keys on groups, not position. |

Two things remain unknown. First, whether `TC3ScopeExportTool.exe` follows export settings
saved in a project: a `.svdx` carries an `<AutoSaveExportConfigurationString>` with a
`CSVProperties` block, and it was empty in the one real file inspected. Second, whether
Scope View's defaults match the table above. Report any other layout with
`manifest --dump-header`, redacted per `examples/README.md`.
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
one machine, one tool version, and the `;` delimiter has yet to appear in a real file. The
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
