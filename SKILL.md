---
name: twincat-scope
description: "Record and analyse TwinCAT 3 Scope measurements. Trigger whenever the user works with: TwinCAT Scope, Scope View, TE1300, TF3300, Scope Server, .svdx, .tcscopex, .svd, .tcmproj, a scope project, a trace, a recording, a measurement, an oscilloscope view of PLC data, channels, sample rate, oversampling, a scope trigger, or exporting scope data to CSV/TDMS. Also trigger for diagnosing machine behaviour from recorded data: following error, position lag, torque spikes, velocity saturation, jitter, cycle-time overruns, axis oscillation, drive tuning, 'why did the axis fault', 'what happened at 12 seconds', or any request to scan, summarise or find events in a large measurement file. Also trigger when a directory contains .tcscopex or .svdx files even if the user does not say TwinCAT. Do NOT use for WRITING or REVIEWING Structured Text or PLC code - this skill is for measurement and diagnosis, not authoring. Do NOT use for Siemens or Rockwell trace tools."
---

# twincat-scope — measure a machine, then actually read the measurement

> **Reference material only. Not for safety functions.** Every scope configuration, recording
> plan and diagnosis you produce must be reviewed and validated by a qualified engineer
> against the drive and platform documentation before anyone acts on it — say so when you
> hand one over.

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
4. **Convert with `ingest`, once.** Every later verb then runs in seconds against Parquet
   instead of minutes against CSV. Without `-o` the Parquet goes to the cache dir
   (`%LOCALAPPDATA%\tcscope\cache`, `$XDG_CACHE_HOME/tcscope` elsewhere); `output` names it —
   pass that path to every later verb.
5. **A CSV exported from Scope View by hand depends on the user's export settings.** Ask for
   them, or advise the ones in `references/export-tool.md` (*Exporting from Scope View by
   hand*). A channel drawn in several tabs exports several times; exact copies are collapsed
   and listed under `copies_collapsed`. The `Offset` header row is part of the channel's
   scaling, reported as `scale_offset`, and the both-readings rule below applies to it.

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
both — a confident wrong diagnosis costs a day on the shop floor. Quote an error code only
if it is in the recording or in a source you name; never give "for example" NC or drive
error IDs from memory — they look authoritative and get looked up as fact.

## Workflow — building a recording

```bash
py -3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex \
    -o MyScope.tcscopex \
    --channels "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbStation.sbBlocked:BOOL,Axes.Axis1.ActPos" \
    --netid 1.2.3.4.1.1 --sample-time-ms 1 --record-time 120

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
- **Keep the sample time a multiple of the task cycle.** When recording starts, Scope rounds
  each acquisition's sample time **down** to a whole multiple of its own task's cycle, and a
  time below one cycle becomes one cycle — silently. 7.5 ms recorded at 4 ms on a 4 ms PLC task
  and at 6 ms on a 2 ms NC task in the same file. The `.tcscopex` keeps the written value until
  a save after a recording, so read the recorded rate from `manifest`, not from the file.

`newscope` also lays the file out — one chart tab per device, one stacked band per quantity,
at most eight traces per band, flags on 0/1 — because everything sharing an axis shares one
auto-scaled range, and a following error of microns disappears under a position of a metre.
It prints the layout it chose: check it before handing the file over. `--layout flat` is for
channels that genuinely share a scale, and a layout is changed by regenerating, not by
editing the XML. Colours are written absolutely: `--theme auto` (default) follows the TwinCAT
XAE Shell's theme where it can read it, else `dark`, which read well with the IDE in both
themes; `--theme dark|light` forces one. `references/scope-configuration.md`.

**Always `checkscope` before handing a file over.** It catches the failures that look like
success — a display channel wired to nothing opens perfectly and plots an empty chart, a
symbol on the wrong port never resolves, an IEC type is refused as `VOID`, and shared or
placeholder names export as columns nobody can tell apart — and it warns on recording load
and on a fixed window, which is a lottery ticket for an intermittent fault. `trigger_action`
is `TriggerAction` exactly as the file writes it; `NONE` (Scope View's *Set Mark*) and the
display, export and reporting actions leave a fixed window even when a trigger is configured.
A ring buffer (`ring_buffer`: Scope View's *Ringbuffer*, saved as `StopMode` `ClientStop`) is
never a fixed window: it keeps the last `RecordTime` until someone stops it.

With the PLC project at hand, add `--tmc <PLC>.tmc` — every PLC symbol is then checked
against the compiled program: typos, renamed variables, whole blocks, and types read at the
wrong width. The `.tmc` reader has been run against one real 862-symbol program; on another,
treat a surprising result as a finding about the reader. `references/scope-configuration.md`.

Then stop: opening the file in Scope View and pressing Record is the human's move (rule 4).
Tell them to **add it to an existing TwinCAT Measurement project** — double-clicked on its
own, one hung in the new-project wizard. Generated files carry fresh GUIDs, so two can share
a project; a hand-copied file cannot. Have them save the `.svdx` before changing any setting:
a change after Record discards the unsaved recording.

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

**Target:** TwinCAT 3 Scope — TE1300 Scope View and TF3300 Scope Server. Everything verified
came from field sessions on real machines (`evals/field-review-*.md`).

**Verified:** generated files, unedited, **record** — NC axis channels on 501 and PLC
`BIT`/`INT16`/`REAL64` on 851 — and the whole path ran once end to end: trigger, real export
tool, `ingest`, `manifest`. The CSV reader handled 19 genuine exports and every CSV option in
Scope View's dialog, reading each layout or refusing it by name. `checkscope` has read 25 real
project files, including eight trigger actions and ring-buffer mode; a ring buffer keeps
exactly its record time, ending at the stop. Both templates open as shipped. `--tmc` caught
every planted error against a real `.tmc`. NC channels by every path `newscope` types (direct
axis fields, `ToPlc`/`FromPlc` members) record on a moving axis and keep their types.
Timelines *All* on a multi-channel group reads correctly. `events` reports an axis on an end
stop as one `standing` and leaves a real settling tail after arrival out. `manifest`'s
scaling warning fires on a real Scope View export and names only the scaled channel.

**Not verified:** the analysis verbs across many real recordings (most real data is from one
machine), what a *Subsave* trigger records (it needs a Professional licence), marker tables in
an export, and a channel that genuinely saturates (an axis parked at a software limit or on an
end stop is verified: no `clipping`). A CSV exported from Scope View with *Scale values* on
cannot be told from a raw one — `manifest` warns when scaling is set. Until the export setting
is known, give **both readings** (the value as it stands, and factor × value + offset) and do
not treat raw as the real quantity; prefer `ingest` on the `.svdx`, then scale once. Rule 3 applies to this skill's own claims: report at exactly that precision.
