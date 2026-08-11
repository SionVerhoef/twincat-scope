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
   TwinCAT installation on this machine. Say "this has not been opened in TwinCAT" rather
   than implying it has.
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
python3 scripts/tcscope.py doctor           # works with nothing installed
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
question instead.

### 4. Report

What the data shows · which channel and which timestamp · what you did **not** check ·
what the human should do next. If the evidence is consistent with two different causes, say
both — a confident wrong diagnosis costs a day on the shop floor.

## Workflow — building a recording

```bash
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbAxis.NcToPlc.PosDiff" \
    --netid 192.168.1.10.1.1 --sample-time-ms 1

python3 scripts/tcscope.py checkscope MyScope.tcscopex
```

Always `checkscope` before handing a file over. It catches the failure that looks like
success: a display channel whose `AcquisitionGUID` points at nothing still opens perfectly
and plots an empty chart.

Then stop. Opening it in Scope View and pressing Record is the human's move — see rule 4.

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
templates are validated against that schema. **Nothing has been opened in TwinCAT**, because
no Beckhoff toolchain exists in the environment this was built in. The CSV reader has not
been run against genuine `TC3ScopeExportTool.exe` output either; it sniffs the format
defensively and says what it detected. Rule 3 applies to this skill's own claims — the
analysis verbs are tested against synthetic fixtures with planted defects, and that is
exactly as much as it proves.

The highest-value contribution is a real exported CSV: drop one in `tests/fixtures/` and the
reader stops guessing.
