# Field review — main @ 1fa0e9b

Run by an agent during a real debugging session on a running Beckhoff machine — not a review
pass. `twincat-scope` @ `1fa0e9b` and the sibling `twincat-st` @ `e37279b`, installed as global
skills in `~/.claude/skills/` (plugins were not available on that workstation). Windows 10 Pro
19045, Python 3.12.10, uv 0.12.7, TwinCAT 3 with the TF3300 Scope Server,
`TC3ScopeExportTool.exe` present. The target was a linear-motor transport loop whose movers
run as NC modulo axes, programmed in an in-house PLC framework that uses a Hungarian-style
prefix convention (`sb`/`se`/`sf`, `ib`/`ob`, …). The task: diagnose a repeating startup
fault, then build a better recording.

**Anonymised.** The AMS net ID, symbol paths, axis names, drive tags, channel aliases and the
framework name below are stand-ins. Recording figures — channel counts, port counts, sample
rates, row counts, skews and colour values — are as measured. Machine process timings (the
homing duration, the PLC cycle) are generalised rather than stated, since they describe the
machine and not the recording.

## Verdict

**The analysis half worked. The generator half did not: `newscope` produced a file that could
not record at all, and `checkscope` passed it with `ok: true`.** That is the headline.

Found by generating a 53-channel file from `templates/axis-diagnosis.tcscopex` and running it
on the target. Every channel had the wrong data type, the wrong variable size and a
placeholder name, and every axis channel was looked up on the wrong ADS port. `checkscope`
warned only about chart crowding and the missing trigger.

This answers item 2 of the real-machine test runbook ("does a generated file open, and does
it record?"): it opens, and it does not record.

## Findings — `newscope`

Ranked by how badly they break a recording.

### N1 — one `TargetPort` for every channel (showstopper)

TwinCAT serves NC axis symbols and PLC symbols from different ADS ports:

| Symbol namespace | Port |
|---|---|
| `Axes.*` (NC) | 501 |
| PLC symbols (`MAIN.…`, `GVL.…`) | 851 |

`newscope` writes one `<TargetPort>` everywhere (`--port`, default 851). The PLC channels
resolved; every axis channel failed with:

```
'TwinCAT Scope View': Symbolname could not be found for channel:  '"Axis1_SetPosModulo" (Axes.Mover 1 (Drive1_ChA).SetPosModulo)'
```

The symbol name was right all along — it was looked up in the wrong runtime. Cost: two round
trips to the machine.

Confirmed against a file authored by hand in Scope View in the same project: 12 axis channels
on port 501, 26 PLC channels on port 851.

**Fix:** derive the port per channel from the namespace (`Axes.` → 501, else the PLC port), or
let `--port` take a mapping.

### N2 — `DataType` copied from the template, so every channel gets one type

All 53 channels came out `LREAL` because the template is all-`LREAL`. The real symbols were a
mix of booleans, `INT` enums and `LREAL`. Scope reads 8 bytes from a 1-byte `BOOL`.

**Fix:** classify per symbol. In this codebase a prefix rule matched all 38 channels of the
hand-authored file: `sb*`/`ob*`/`ib*` → bit, `se*`/`sn*` → int16, `sf*`/`if*`/`of*` and NC
values → real64. Better: resolve types from the compiled `.tmc` (see C5) — a prefix rule is
one house style, not a TwinCAT rule.

### N3 — the template's `DataType` vocabulary is wrong

The more serious half of N2. Scope does not use IEC type names:

| IEC | Scope `<DataType>` | `<VariableSize>` |
|---|---|---|
| `BOOL` | `BIT` | 1 |
| `INT` | `INT16` | 2 |
| `LREAL` | `REAL64` | 8 |

`LREAL`, as shipped in `templates/axis-diagnosis.tcscopex`, appears in **none** of the 7
Scope-View-authored `.tcscopex` files in the project. The reviewer first "fixed" N2 with
`BOOL`/`INT`/`LREAL`, which was still wrong; only a field-by-field comparison with a working
file showed the real vocabulary. If `DataType` was wrong, audit every other field of the
template against a genuine file too.

### N4 — `VariableSize` fixed at 8

Same root cause as N2. Must follow the type: 1 / 2 / 8.

### N5 — `<Name>` left as the placeholder `Signal`

`<Name>` is the Scope tree label **and the CSV column header on export**. A 53-channel
recording exported 53 columns all called `Signal`. The user spotted it independently: *"All
signals are called signal an i think they need a name"*.

A hand-authored file uses short unique aliases (`Station_seStep`, `Station_obBlocked`,
`Axis1_ActVelo`) with the full symbol path in `<Title>`. `newscope` should derive a short
unique alias from the symbol and keep the path in `Title`.

### N6 — no way to set the record window

`<RecordTime>` is baked in at 60 s (`600000000`, 100 ns ticks) and there is no
`--record-time`. The event of interest, a homing sequence, ran past 60 s on some attempts, so
the default window could not contain it. The reviewer hand-patched the XML. `checkscope` does
warn about a fixed window with no trigger — the right warning, with no supported way to act
on it.

### N7 — chart bands don't understand prefix-style PLC names

The per-device / per-quantity layout is a genuinely good feature for NC axes. For PLC struct
paths it made one chart per FB, and a 21-member FB became one chart with 21 channels on one
axis — which `checkscope` then warned about. Suggested: classify prefix-style leaves by prefix
(`se*` step/state, `sb*` bool, `sf*` distance/position) as well as by keyword.

## Findings — `checkscope` caught none of the above

In rough order of value:

- **C1** `Axes.*` symbols on a non-NC port — or flag one port used for both namespaces.
- **C2** `<DataType>` outside the Scope vocabulary. `LREAL`/`BOOL`/`INT` should be a hard error
  with "did you mean `REAL64`/`BIT`/`INT16`".
- **C3** `<VariableSize>` inconsistent with `<DataType>`.
- **C4** duplicate or placeholder `<Name>` values (`Signal`, empty, repeated) — they silently
  ruin a CSV export.
- **C5** optional `--tmc <PLC>.tmc`: resolve every PLC symbol against the compiled symbol
  table. Done by hand with `grep` in this session, it confirmed at once which symbols existed,
  and would have caught everything except N1 before walking to the machine.

The status line says `checkscope` was run against 7 real project files. That validated
*reading* them, not *generating* an equivalent. Wanted: a round-trip test that generates a
file and asserts its field-by-field shape matches a real one.

## Theming — new requirement from the user

> "i am now in dark mode in twincat and the scopes look a little bit whitish and ugly but they
> have to look nice for both dark and light theme or switch"

From the files alone — **nothing here was checked visually**:

- Generated files contain no `<ForeColor>` and no `<GridColor>`. A hand-authored file has
  `GridColor` `-921103` (`0xFFF1F1F1`, near-white) and `ForeColor` `DarkSlateGray`.
- Colours are stored as absolute .NET ARGB signed int32 (`-16744448` = `0xFF008000`) or as
  .NET colour names. No theme token or "auto" value is visible in the schema, so one file
  cannot follow the editor theme — unless Scope supplies theme-aware defaults for omitted
  elements.

Questions, in order:

1. **Does Scope theme the chart itself when `ForeColor`/`GridColor`/`DisplayColor` are
   omitted?** If yes, the fix is to stop writing them. Needs a real TwinCAT; the most valuable
   single thing to test.
2. If not, `newscope --theme light|dark` with two vetted palettes.
3. Either way, never emit `Black` or pure white for a trace. Mid-tone saturated hues that
   hold contrast on both a white and a near-black ground make the theme switch cosmetic.

## Docs, tooling, environment

- **`python3` vs `py -3`.** `twincat-st/SKILL.md` writes every command as `py -3` because
  Windows has no `python3`. `twincat-scope/SKILL.md` uses `python3`, and `doctor`'s closing
  hint prints a `python3 …` command. On this workstation `python3` hit the Microsoft Store
  alias ("Python was not found") despite a working 3.12.10.
- **`doctor` was accurate** — found `uv` missing and located `TC3ScopeExportTool.exe`.
- **`python -m pytest` collects nothing from `tests/test_verbs.py`** (exit 5). A contributor
  running pytest will think the suite is empty.
- `tools/update-skill.ps1` assumes a release exists; there were none, so the git-clone path
  was used. The README could say so.

## What worked — do not regress it

- **The `manifest → stats → events → plot → window` ladder.** It took an 80 s, 40-channel,
  38k-row export down to the single PLC cycle where the fault happened, without dumping
  samples.
- **The acquisition-group timing block.** The export had two groups (500 Hz / 250 Hz);
  `row_is_one_instant: false`, `max_skew_ms: 2.0`, `cross_group_timing_valid: true` said
  exactly how much cross-channel ordering could be trusted. The reviewer would have got this
  wrong by hand.
- **`events`** found the two fault instants with no tuning.
- **`plot`'s min/max envelope** made a 40k-sample overview readable in one image.
- **`checkscope`'s crowding and no-trigger warnings** — good judgement, well phrased.
- **"Never hand back samples"** (`references/data-triage.md`) held up under real use.

## `twincat-st` notes

Belong to the sibling repository; recorded here because they came from the same session.

- `tcpou.py get/set/check` was flawless across ~8 edits to two large `.TcPOU` files — GUIDs,
  `<LineIds>`, CRLF and the missing BOM all preserved, no spurious `check` findings.
- The `X9` direction-prefix fix in `e37279b` mattered here: this codebase is exactly the
  `ibEnable`/`obDone` style the old anchored patterns missed.
- **Possible new rule:** an edit left a multi-line comment with `//` on the first line only,
  so three bare prose lines sat inside a `VAR` block. `st_review` did not flag it. "A line
  inside `VAR…END_VAR` that is neither a declaration nor a comment" would catch a class of
  machine-edit and merge accidents that today only surface at compile time.
- `--min-severity medium` on an application folder: 0 high / 5 medium on ~1800 lines — good
  signal to noise. "Scan the application folder, not the `.plcproj`" is the right advice.

## Reproducing the generator defects

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o Test.tcscopex \
    --channels "MAIN.fbStation.seStep,MAIN.fbStation.sbFlag,Axes.Axis1.SetPosModulo" \
    --netid 1.2.3.4.1.1 --sample-time-ms 10
py -3 scripts/tcscope.py checkscope Test.tcscopex     # ok: true
```

In `Test.tcscopex`: all three `<DataType>` are `LREAL` (should be `INT16`, `BIT`, `REAL64`),
all three `<VariableSize>` are `8` (should be `2`, `1`, `8`), all three `<TargetPort>` are
`851` (the axis should be `501`), all three channel `<Name>`s are `Signal`, `<RecordTime>` is
`600000000` with no flag to change it, and there is no `<ForeColor>` or `<GridColor>`.

## Checked in the repo afterwards

By the maintaining agent, on Linux, without TwinCAT:

- **Reproduced** the command above exactly as described: `ok: true`, and every listed field
  as stated. `newscope --help` offers `--port` and nothing for record time or theme.
- **Correction to the theming notes.** `newscope` does give each channel element its own
  palette colour (the first is `-14714956` = `0xFF1F77B4`), but the
  `ChannelStyle` child, time axis, value axis and marker container all still say `Black`, and
  the chart and axis-group elements carry hard-coded light greys (`-1118482` = `0xFFEEEEEE`,
  `-1973016` = `0xFFE1E4E8`). Those greys are a likelier cause of the "whitish" look than the
  trace colour. Which of the two per-channel `DisplayColor`s Scope draws the trace with is
  unverified.
- **N7's cause.** Tabs come from the symbol path minus its leaf; bands come from keywords in
  the leaf (`pos`, `velo`, `flag`, `state`, …). Prefix-style leaves such as `seStep` or
  `sfDistance` match no keyword and fall into `Other`, so a prefix-style FB collapses into one
  band.
- **pytest.** `tests/test_verbs.py` is a script with a `__main__` runner and no `test_*`
  functions; it runs as `python3 tests/test_verbs.py`, which the README says.

## Not checked by this review

Whether omitted colour elements get theme-aware defaults; whether `BIT`/`INT16`/`REAL64` plus
per-namespace ports is the *complete* set of changes a generated file needs to record (other
template fields were not audited). `ingest` and `correlate` were not exercised in the session
as reported.
