---
name: twincat-scope
description: "Record and analyse TwinCAT 3 Scope measurements. Trigger whenever the user works with: TwinCAT Scope, Scope View, TE1300, TF3300, Scope Server, .svdx, .tcscopex, .svd, .tcmproj, a scope project, a trace, a recording, a measurement, an oscilloscope view of PLC data, channels, sample rate, oversampling, a scope trigger, or exporting scope data to CSV/TDMS. Also trigger for diagnosing machine behaviour from recorded data: following error, position lag, torque spikes, velocity saturation, jitter, cycle-time overruns, axis oscillation, drive tuning, 'why did the axis fault', 'what happened at 12 seconds', or any request to scan, summarise or find events in a large measurement file. Also trigger when a directory contains .tcscopex or .svdx files even if the user does not say TwinCAT. Do NOT use for WRITING or REVIEWING Structured Text or PLC code - this skill is for measurement and diagnosis, not authoring. Do NOT use for Siemens or Rockwell trace tools."
---

# twincat-scope — measure a machine, then actually read the measurement

Recording is the easy half. Ten minutes of twenty channels at 1 kHz is twelve million
samples — far too large to read, and the thing you are looking for is usually three samples
wide. So this skill never hands back samples: it hands back summaries, events and pictures,
and only returns real rows once a time range is known.

**Not for authoring code.** This skill measures and diagnoses. Once the data has named a
fault, writing the PLC fix is a different job — hand off to whatever covers ST authoring in
this project.

## The four rules

1. **Never author safety logic.** No TwinSAFE, no FSoE, no safety-PLC configuration, and
   never present standard PLC code as a safety function. Reading and explaining existing
   safety configuration is fine; recording a safety signal for diagnosis is fine.
2. **Never write to or activate a live machine.** Reading measurements is safe. Writing a
   variable, activating a configuration, or switching Run/Config mode is a human gesture —
   propose the command, do not run it.
3. **Never claim something is verified that you have not verified.** There is very likely no
   TwinCAT installation on this machine. What has and has not been seen working in TwinCAT
   is under *Status* below — report at that precision, never rounded up to "works".
4. **A recording is not free.** Sample rate × channel count consumes real-time bandwidth on
   the target, and an over-specified scope can disturb the very machine it is diagnosing.
   Propose the configuration; a human starts it — `references/recording-load.md`.

## Architecture

| File | Read it when |
|---|---|
| **`references/data-triage.md`** | **Any time you look at recorded data.** The method — how to get from twelve million samples to one answer. Highest-value file here. |
| `references/recording-load.md` | Before proposing any recording. Rule 4, and how to size a scope. |
| `references/scope-configuration.md` | Building or editing a `.tcscopex`. Schema, ports, types, layout, GUID linkage. |
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
`doctor` first — it names the fix. `py -3` is the Windows launcher, and TwinCAT runs on
Windows; on Linux or macOS (and in this repo's CI) the same commands are `python3`.

## Workflow — diagnosing from a recording

1. **`manifest` first, always.** It names the channels, units, sample rate, duration and
   gaps rather than letting you guess them — and every frequency claim downstream is scaled
   by that rate. `manifest --dump-header` shows the raw first lines when a CSV looks mangled.
2. **Read the `timing` block before comparing any two channels.** A Scope CSV is several
   acquisition groups side by side, each on its own clock, so a physical row is not one
   instant; `cross_group_timing_valid: false` means the export is broken and no cross-group
   timing claim from it means anything — say so and re-export. `references/data-triage.md`.
3. **Times are reported in seconds** everywhere, converted from the export's milliseconds.
4. **Convert the `.svdx` with `ingest`, once** — everything downstream runs in seconds
   against Parquet instead of minutes against CSV. The export tool's intermediate CSV goes to
   the cache dir (`%LOCALAPPDATA%\tcscope\cache`, `$XDG_CACHE_HOME/tcscope` elsewhere),
   never beside the `.svdx`; `intermediate_csv` names it. Don't use Scope View's own CSV export: it
   drops the symbol, port, type and offset rows (`references/export-tool.md`). Exact copies
   of a channel drawn in several tabs are collapsed and reported (`copies_collapsed`), and a
   `display_offset` is where a trace was drawn — never add it to the values.

Then descend the ladder — never skip to the bottom:

| Step | Verb | What it answers |
|---|---|---|
| 1 | `manifest` | What is in this file? |
| 2 | `stats` | Which channel looks wrong? |
| 3 | `events` | When did something happen? |
| 4 | `plot` | What does it look like around then? |
| 5 | `correlate` | Which channel moved first? |
| 6 | `window` | What were the actual numbers? |

- `window` is last on purpose and refuses ranges wider than its row cap — wanting it wider
  means you skipped a rung; go back to `events` or `plot` and narrow the question.
- `plot` draws a min/max envelope per pixel bucket, never decimation — a decimated chart
  hides a three-sample spike about six times out of seven. `references/data-triage.md`.
- `correlate` refuses pairs from different groups unless `--allow-cross-group` resamples
  them (and says so). A **negative** `lag_seconds` means `a` leads `b`, and `a` is
  whichever channel comes first in `--channels` — swap the order and the sign flips.
- `--channels` matches the short `name` or the qualified `symbol_name`; two groups routinely
  share a short name, so quote the qualified path when you need to be exact.

**Report:** what the data shows · which channel and which timestamp · what you did **not**
check · what the human should do next. If the evidence is consistent with two causes, say
both — a confident wrong diagnosis costs a day on the shop floor.

## Workflow — building a recording

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbStation.sbBlocked:BOOL,Axes.Axis1.ActPos" \
    --netid 192.168.1.10.1.1 --sample-time-ms 1 --record-time 120

py -3 scripts/tcscope.py checkscope MyScope.tcscopex
```

Four things decide whether the file records at all — detail and field history for each in
`references/scope-configuration.md`:

- **The port follows the symbol.** `Axes.…` is served by the NC runtime on 501, everything
  else by `--port` (851); one port for both fails every axis channel with "Symbolname could
  not be found". A per-channel `SYMBOL:TYPE:PORT` overrides it, and is how a second PLC
  runtime (852, 853…) is reached.
- **The type must be Scope's, not IEC's.** Declare it per channel (`:BOOL`, `:INT`,
  `:LREAL`); known NC axis fields are typed automatically; anything else undeclared is
  written `REAL64` and reported as *defaulted* — wrong for a `BOOL`, which then records
  nothing usable.
- **The window must contain the event.** `--record-time <seconds>`; the templates ship 60 s,
  and a homing sequence alone can outrun that.
- **The sample time snaps to the task cycle.** Pick a multiple of the cycle of the task that
  owns the channels, and read the rate that was recorded back from `manifest`.

`newscope` also lays the file out — one chart tab per device, one stacked band per quantity,
at most eight traces per band, flags on 0/1 — because everything sharing an axis shares one
auto-scaled range, and a following error of microns disappears under a position of a metre.
It prints the layout it chose: check it before handing the file over. `--layout flat` is for
channels that genuinely share a scale, and a layout is changed by regenerating, not by
editing the XML. Colours are written absolutely (`--theme dark` default, or `light`); a
dark-styled file read well with the IDE in both themes. `references/scope-configuration.md`.

**Always `checkscope` before handing a file over.** It catches the failures that look like
success — a display channel wired to nothing opens perfectly and plots an empty chart, a
symbol on the wrong port never resolves, an IEC type is refused as `VOID`, and shared or
placeholder names export as columns nobody can tell apart — and it warns on recording load
and on a fixed window, which is a lottery ticket for an intermittent fault. `trigger_action`
is `TriggerAction` exactly as the file writes it; `NONE` with no restart is a fixed window
even when a trigger is configured.

With the PLC project at hand, add `--tmc <PLC>.tmc` — every PLC symbol is then checked
against the compiled program: typos, renamed variables, whole blocks, and types read at the
wrong width. The `.tmc` reader has not yet met a real file, so treat a surprising result as
a finding about the reader. `references/scope-configuration.md`.

Then stop: opening the file in Scope View and pressing Record is the human's move (rule 4).
Tell them to **add it to an existing TwinCAT Measurement project** — double-clicked on its
own, one hung in the new-project wizard. Generated files carry fresh GUIDs, so two can share
a project; a hand-copied file cannot.

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

## Status

**Target:** TwinCAT 3 Scope — TE1300 Scope View and TF3300 Scope Server. There is no
Beckhoff toolchain where this skill is developed; everything verified came from field
sessions, written up in `evals/field-review-*.md` and summarised in the README's *Status*.

Verified: unedited generated files **recorded** on a real machine — NC axis channels on 501
and PLC `BIT`/`INT16`/`REAL64` on 851, with the dark theme, and once end to end through a
Scope View trigger, the real export tool and `ingest`/`manifest`. The CSV reader was
measured against 19 genuine exports (both dialects, all three alignment states);
`checkscope` has read 7 real Beckhoff-authored projects.

Not verified: the analysis verbs against the variety of those 19 exports (one real recording
so far), and the `;` delimiter in a real file. Rule 3 applies to this skill's own claims:
report at exactly that precision.
