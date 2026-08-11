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

`tcscope.py ingest` calls this for you when handed a `.svdx`, then converts to Parquet.

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

**This reader has not been validated against genuine export-tool output.** It sniffs the
format and reports what it detected. If something looks wrong, `manifest --dump-header` shows
the raw first lines — trust those over the sniffer.

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

The single most useful thing anyone can add to this skill is one CSV produced by a real
`TC3ScopeExportTool.exe`, from any short recording. Values can be redacted freely — only the
header structure matters. Drop it in `tests/fixtures/` and the reader stops guessing.

Before committing anything from a real machine, read `examples/README.md` — recordings carry
more identifying detail than people expect.
