---
name: twincat-scope
description: "Record and analyse TwinCAT 3 Scope measurements. Trigger whenever the user works with: TwinCAT Scope, Scope View, TE1300, TF3300, Scope Server, .svdx, .tcscopex, .svd, .tcmproj, a scope project, a trace, a recording, a measurement, an oscilloscope view of PLC data, channels, sample rate, oversampling, a scope trigger, or exporting scope data to CSV/TDMS. Also trigger for diagnosing machine behaviour from recorded data: following error, position lag, torque spikes, velocity saturation, jitter, cycle-time overruns, axis oscillation, drive tuning, 'why did the axis fault', 'what happened at 12 seconds', or any request to scan, summarise or find events in a large measurement file. Also trigger when a directory contains .tcscopex or .svdx files even if the user does not say TwinCAT. Do NOT use for WRITING or REVIEWING Structured Text or PLC code - this skill is for measurement and diagnosis, not authoring. Do NOT use for Siemens or Rockwell trace tools."
---

# twincat-scope — measure a machine, then actually read the measurement

Recording is the easy half. The hard half is that a scope file is far too large to look at.

Ten minutes of twenty channels at 1 kHz is twelve million samples. Reading it into a
conversation is impossible, and skimming it is worse than useless — the thing you are
looking for is usually three samples wide, and every shortcut that makes the file small
enough to skim is a shortcut that deletes it.

So this skill never hands back samples. It hands back summaries, events and pictures, and
only returns real rows once a time range is known.

**Not for authoring code.** This skill measures and diagnoses; it does not write or review
Structured Text. Once the data has named a fault and the fix is in the PLC program, that is a
different job — hand off to whatever covers ST authoring in this project.

## The four rules

1. **Never author safety logic.** No TwinSAFE, no FSoE, no safety-PLC configuration, and
   never present standard PLC code as a safety function. You may read and explain existing
   safety configuration. Recording a safety signal for diagnosis is fine; changing one is not.
2. **Never write to or activate a live machine.** Reading measurements is safe. Writing a
   variable, activating a configuration, or switching Run/Config mode is a human gesture —
   propose the command, do not run it.
3. **Never claim something is verified that you have not verified.** There is very likely no
   TwinCAT installation on this machine. What this skill's own output has and has not been
   seen doing in TwinCAT is under *Status and scope* below — report that, and do not round it
   up to "works".
4. **A recording is not free.** Sample rate × channel count consumes real-time bandwidth on
   the target. An over-specified scope can disturb the very machine it is diagnosing, which
   corrupts the measurement and the process at the same time. **Propose the configuration;
   a human starts it on production.** See `references/recording-load.md`.

## Architecture

| File | Read it when |
|---|---|
| **`references/data-triage.md`** | **Any time you look at recorded data.** The method — how to get from twelve million samples to one answer. Highest-value file here. |
| `references/recording-load.md` | Before proposing any recording. Rule 4, and how to size a scope. |
| `references/scope-configuration.md` | Building or editing a `.tcscopex`. Schema, channels, GUID linkage. |
| `references/export-tool.md` | Getting data out of a `.svdx`, and the CSV traps. |

Plus `scripts/tcscope.py` (every verb), `templates/` (known-good `.tcscopex`), `examples/`
(real recordings — empty by design), `tests/` (synthetic fixtures with planted defects).

## Running the tool

```bash
uv run scripts/tcscope.py <verb> ...        # analysis verbs need dependencies
py -3 scripts/tcscope.py doctor             # works with nothing installed
```

`doctor`, `newscope` and `checkscope` deliberately need no third-party packages, so the
acquisition half works on a machine that has never seen `uv`. If anything is missing, run
`doctor` first — it names the fix.

## Workflow — diagnosing from a recording

### 1. Orient before analysing

`manifest` first, always. It costs nothing and tells you what you actually have: channels,
units, sample rate, duration, gaps, and whether a channel is dead. Guessing the sample rate
and then reasoning about frequencies is a good way to be confidently wrong.

If the CSV looks mangled, `manifest --dump-header` shows the raw first lines. The reader
sniffs the delimiter and decimal separator, which is not the same as knowing them.

**Read the `timing` block before you compare any two channels.** A Scope CSV is not one
table — it is several acquisition groups laid side by side, each with its own time column
and often its own sample rate, so *a physical row is not one instant in time*:

```
<t0> <a0> <a1> | <t1> <b0> <b1> <b2> | <t2> <c0>
^ group 0      ^ group 1             ^ group 2
```

Every channel is timestamped from its own group. `manifest` reports per group: declared and
measured `sample_time_ms`, `repeat_factor`, `t_first`, `t_last`, `n_samples`. Then:

| Field | Means |
|---|---|
| `row_is_one_instant: true` | all groups agree exactly; the file behaves like one table |
| `max_skew_ms` | worst row-wise disagreement between any two group clocks |
| `cross_group_timing_valid: false` | **the export is broken.** Slow groups were never repeat-padded, so they run off their own wall clock. No cross-group timing claim from this file means anything — say so and re-export. |

Times in a Scope export are milliseconds. This tool converts on read and reports **seconds**
everywhere (`time_unit: "ms"`, `times_reported_in: "s"`).

### 2. Convert once

```bash
uv run scripts/tcscope.py ingest rec.svdx -o rec.parquet
```

Everything downstream is faster against Parquet, and `.svdx` needs the export tool anyway.

### 3. Descend the ladder — never skip to the bottom

| Step | Verb | What it answers |
|---|---|---|
| 1 | `manifest` | What is in this file? |
| 2 | `stats` | Which channel looks wrong? |
| 3 | `events` | When did something happen? |
| 4 | `plot` | What does it look like around then? |
| 5 | `correlate` | Which channel moved first? |
| 6 | `window` | What were the actual numbers? |

`window` is last on purpose and refuses ranges wider than its row cap. If you find yourself
wanting to widen it, you skipped a step — go back to `events` or `plot` and narrow the
question instead. It returns one block per acquisition group; a flat `rows` list appears
only when your selection lives in a single group, because rows from different groups do not
share a timestamp.

`correlate` refuses pairs from different groups unless you pass `--allow-cross-group`, which
resamples onto a common axis and says so in the output. A **negative** `lag_seconds` means
`a` leads `b`.

Channels carry both a short `name` (the selector) and the qualified `symbol_name` path.
`--channels` matches either, which matters because two groups routinely hold the same short
name. Quote the qualified path when you need to be exact.

### 4. Report

What the data shows · which channel and which timestamp · what you did **not** check ·
what the human should do next. If the evidence is consistent with two different causes, say
both — a confident wrong diagnosis costs a day on the shop floor.

## Workflow — building a recording

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbStation.sbBlocked:BOOL,Axes.Axis1.ActPos" \
    --netid 192.168.1.10.1.1 --sample-time-ms 1 --record-time 120

py -3 scripts/tcscope.py checkscope MyScope.tcscopex
```

Three things decide whether the file records at all, and none of them are visible until you
are stood at the machine:

- **The port follows the symbol.** `Axes.…` is served by the NC runtime on 501, everything
  else by `--port` (851). `newscope` splits them; one port for both is why a file whose symbol
  names are all correct still reports "Symbolname could not be found". Override it per channel
  with a third field — `SYMBOL:TYPE:PORT` — which is also how a second PLC runtime (852, 853…)
  is reached. A PLC symbol on a port below 851 answers nowhere; both verbs say so, because
  `--port 85` is a file that opens and records nothing.
- **The type has to be Scope's, not IEC's.** Give it per channel — `SYMBOL:BOOL`, `:INT`,
  `:LREAL` — and it is written as `BIT`/`INT16`/`REAL64` with the matching width. Scope read
  `LREAL` itself as `VOID` and refused the channel. Known NC axis fields (`Axes.<axis>.ActPos`,
  `….ErrorCode`) get their NC type without being asked. Any other channel with no type
  declared is written as `REAL64` and reported as *defaulted*; on a `BOOL` that reads 8 bytes
  from a 1-byte variable and records nothing usable.
- **The window has to contain the event.** `--record-time <seconds>`; the templates ship 60 s,
  and a homing sequence alone can outrun that.

`newscope` also decides where each channel is drawn, which matters as much as recording it.
Everything sharing an axis shares one auto-scaled range, so twenty channels on one axis is
nineteen flat lines and a following error of a few microns disappears under a position of a
metre. It writes **one chart tab per device** and, inside each tab, **one stacked band per
quantity** — position (set and actual together, since that gap is the measurement), following
error, velocity, acceleration, torque, then bits, then step numbers and counters (apart from
the bits, which a step running to 200 would flatten) — and gives channels sharing a band
different colours. A band that would hold more than eight traces is split into even parts. A
block with a single channel — typically a sequencer's step — does not get a tab of its own: it
is drawn first in the tab of each block beneath it, where it is read, and recorded once. It
prints the layout it chose; check it before handing the file over. `--layout flat` returns to
a single axis for channels that genuinely share a scale.

**Change the layout by regenerating, not by editing the XML.** A generated file came back from
the field with every band disabled and hand-written band names, showing nothing until someone
enabled the bands in Scope View — most likely edited after `newscope` wrote it. If you must
edit one, copy an element that is enabled, and run `checkscope` again afterwards.

Colours are written into the file, and Scope draws them as written: a dark-styled file stayed
dark with the IDE in dark theme and in light, and read well in both. So `--theme dark` (the
default) or `--theme light` picks one background with axis text, grid and traces chosen to
read on it. Whether Scope would theme a colour the file leaves out is still untested.

Always `checkscope` before handing a file over. It catches the failures that look like
success: a display channel whose `AcquisitionGUID` points at nothing opens perfectly and
plots an empty chart; an NC symbol on a PLC port never resolves, and neither does any symbol
on a port no runtime serves; an IEC type name is refused (Scope read `LREAL` as `VOID`), and a
`VOID` already in the file is the mark of Scope having failed to read one; a width that contradicts its
type records the wrong bytes; and channels sharing one name, or left with the template's
placeholder, export as columns nobody can tell apart. It reports the layout and the theme too,
says when a chart is too crowded to read, and warns about anything disabled.

`py -3` is the Windows launcher, and TwinCAT runs on Windows; on Linux or macOS (and in this repo's CI) the same commands are `python3`.

It also reads the capture strategy, which is a separate way to waste a trip to the machine.
A correctly wired project that records a fixed window with no trigger is a lottery ticket for
an intermittent fault — the templates ship with a 60 s window — so `checkscope` warns and
leaves the judgement to you. Wiring and plan fail independently.

Then stop. Opening it in Scope View and pressing Record is the human's move — see rule 4.
Tell them to **add the file to an existing TwinCAT Measurement project** rather than
double-click it: opened on its own, it starts a new-project wizard that hung long enough on
one machine to be abandoned, while added to a project it opened at once. Two generated files
can share a project because `newscope` mints fresh GUIDs every run; a hand-copied file cannot.

## Task routing

| Task | Go to |
|---|---|
| Read, summarise or search a recording | `references/data-triage.md` |
| Decide what to record, or size a scope | `references/recording-load.md` |
| Build or edit a `.tcscopex` | `references/scope-configuration.md` + `newscope` |
| A `.svdx` that will not convert, or a mangled CSV | `references/export-tool.md` |
| Write or review ST / PLC code | Out of scope. Diagnose here, then hand the fix elsewhere |
| Anything TwinSAFE, FSoE or safety-rated | Rule 1. Read and explain only |
| Siemens or Rockwell trace tools | Out of scope. Say so rather than guessing |

## Status and scope

**Target:** TwinCAT 3 Scope — TE1300 Scope View and TF3300 Scope Server.

The `.tcscopex` schema here was derived by reading real Beckhoff sample projects, and the
templates are validated against that schema. It is not written in an environment that has a
Beckhoff toolchain; what has been watched working in TwinCAT came from field sessions.

The first opened a generated project and **recorded nothing**: axis channels on the PLC port,
IEC type names, and every channel named `Signal` (`evals/field-review-1fa0e9b.md`). The second
took one generated file through three rounds (`evals/field-review-1fa0e9b-rounds.md`). An IEC
type was read as `VOID` and refused; with `REAL64`, an axis symbol on 851 was "not found"; with
port 501 as well, **the file recorded** — five `REAL64` NC axis channels, symbolic addressing,
index group and offset left at 0. That file opened, showed its one tab and four bands as laid
out, kept symbol names with spaces and parentheses intact, and recorded.

Those rounds ran patches to an older version. A later session ran this skill's own output,
unedited (`evals/field-review-fe9b487.md`): the same five NC channels, now with an `AxisStyle`
on every axis and the dark theme, **opened and recorded**; and a file mixing two NC axis
channels with a PLC `BOOL`, `INT` and `LREAL` on 851 **recorded all five** across three tabs.
Triggers, `.svdx` conversion and the round trip back through these verbs have not been seen
working.

Rule 3 applies to this skill's own claims, so precisely: the CSV reader **was** measured
against 19 genuine `TC3ScopeExportTool.exe` exports from a Beckhoff CX/AX8000 machine
(TwinCAT 3.1, EU locale) covering both the TAB and `,` dialects, all three
sample-rate alignment states, and multi-line `SymbolComment` values. Those recordings carry
customer machine behaviour and are not in this repo. What is here is
`tests/make_real_fixtures.py`, which regenerates structural copies of all five layouts —
same group boundaries, metadata keys, delimiters, decimal separators and time-column
behaviour, shrunk to 200 rows with synthetic signal. The verbs are tested against those and
against synthetic fixtures with planted defects. `checkscope` was run against 7 real
Beckhoff-authored `.tcscopex` files, which validated *reading* a real project file rather
than *writing* an equivalent one.

What that does **not** prove: no `.svdx` has been converted by the real export tool in this
environment, and a recording from a generated `.tcscopex` has not yet been exported and read
back through these verbs.
