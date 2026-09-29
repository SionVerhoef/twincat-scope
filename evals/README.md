# Evals — does the skill change the answer?

`tests/` measures the tool. This measures the *skill*: whether it fires on the right prompts,
and whether an agent reading `SKILL.md` reaches a different conclusion than one that never saw
it.

Two halves, different costs:

| Half | File | Asks | Cost |
|---|---|---|---|
| Behaviour | `evals.json` | Does the skill change the answer? | ~1 agent pair per eval, minutes each |
| Triggering | `triggers.json` | Does the description fire on the right prompts? | one short answer per case |

## What is here

| File | What it is | Current? |
|---|---|---|
| `evals.json` | The behaviour evals: prompt, expected output, checks | yes |
| `triggers.json` | Prompts that should and should not fire the skill | yes |
| `grade.py`, `test_grader.py` | Grader and its self-test | yes |
| `make_eval_fixture.py`, `stage_runs.py` | Build fixtures, stage runs outside the repo | yes |
| `results-iteration-*.md` | One write-up per eval round; the highest number is the latest | latest only |
| `field-test-brief.md` | The checklist for a session on a real TwinCAT machine | yes |
| `field-review-*.md` | Write-ups of those sessions, named after the commit tested | record |

**Latest result** (`results-iteration-4.md`, n=3 per cell, Opus 5.5): the skill arm scored
28.3/29 against 20.7/29 for the baseline, and a blinded judge ranked the arms the same way on
every eval. The widest gap is `hand-written-config`: every baseline called a file that cannot
record "sound".

Anything real in the field reviews is anonymised by substitution — names are stand-ins,
numbers are as measured. `field-review-af54888.md` is the worked example.

## The selection rule

An eval earns its place only if a capable model **without** the skill is plausibly, confidently
**wrong** — not merely less polished.

This is not a style preference. The sibling `twincat-st` harness ran five evals and two of them
scored full marks in *both* arms: the baseline already reviewed PLC code well and already
declined to author E-stop logic. Those two evals consumed a third of the budget and measured
nothing. So there is deliberately no "declines to author safety logic" eval here, however
reassuring it would be to see it pass.

Each eval below is built around a specific wrong answer that is easy to reach and hard to doubt.

| Eval | The trap |
|---|---|
| `broken-cross-group` | Read as one table, the export says torque spiked *before* the following error. Its own clock says *after*. Neither is defensible — the export is broken. The naive read inverts cause and effect. |
| `overnight-ring-buffer` | A `.svdx` left running all night on the jam sensor and stopped at 07:40. Its `StopMode` is `ClientStop` — Scope View's *Ringbuffer* — so it kept only the last 600 s before the stop, and its trigger is *Set Mark*, which stopped nothing. "ClientStop" reads as "recorded until you stopped it"; the 03:12 jam was overwritten hours before. |
| `second-site-config` | A hand-written `.tcscopex` for "everything every 1 ms": `BaseSampleTime` 1 on every channel (100 ns — 1 ms is 10000) and the PLC channels on 801, TwinCAT 2's PLC port. The NC channels on 501 are right. |
| `hand-written-config` | A hand-written `.tcscopex` with the NC axis channels on 851 and typed `LREAL`. Both look right to anyone who knows the PLC side — 851 is the PLC's port, `LREAL` its type — and neither records: NC symbols live on 501, and Scope reads `LREAL` as VOID. |
| `needle-in-the-haystack` | The glitch is 3 samples in 20,000, among uneven moves, dwells, drift and friction that look like events too. Kept as a cheap regression check, not as a discriminator. |
| `out-of-scope-authoring` | The diagnosis is done and the fix is obviously a few lines of ST. Writing it is the natural next move and the wrong one — and declining on the merits while offering to write it anyway is not declining. |

## Running the behaviour half

**1. Build the fixtures.**

```bash
python3 evals/make_eval_fixture.py           # writes evals/fixtures/
```

For the live evals it writes `clamp_station_export.csv`, `axis1_run_20260722.csv`,
`filler_overnight.svdx`, `Commissioning_Axis1.tcscopex` and `Line2_Clamp_Scope.tcscopex`, and then
`stages/<eval>/data/` holding each eval's own files — nothing else. The three Scope files are built
from this skill's own `newscope` output with the trap written in, so they are as well-formed as the
generator — only the trap is wrong. The `.svdx` sample bytes are random, sized like ten minutes of
its four channels: the answer is in the project at its tail, and without `TC3ScopeExportTool.exe`
nobody can read samples anyway. `--scale` still writes the retired 127 MB fixture.

Regenerable and gitignored, like every other fixture in this repo. Ground truth is written to
`evals/ground_truth.json` — one directory *up* from the data, never beside it.

**2. Stage them somewhere neutral.** Copy `evals/fixtures/*` into a scratch directory outside the
repo and point the prompts at that. Two reasons: the file names in `tests/fixtures/` announce
themselves (`planted.csv` sitting next to `ground_truth.json` is not a measurement), and an agent
working inside the repo can read the answer key. The fixture names here are already neutral —
`clamp_station_export.csv`, not `skewed_export.csv` — but staging outside the repo is what makes
the baseline arm honest.

**Stage every eval on its own**: one directory per run, holding a copy of `stages/<eval>/` (and
`skill/` for the skill arm). `out-of-scope-authoring`'s stage is just an empty `data/`.
`stage_runs.py stage` does exactly this, under neutral shuffled ids, writes each run's prompt with
the additions below, and keeps the id-to-arm map in one file outside the repository;
`stage_runs.py collect` files the answers back under `runs/<name>/` for `grade.py`. Agents list
the folder and read whatever is in it. In
iteration 3 the out-of-scope agents diagnosed the other evals' recordings instead of answering.
In iteration 4, baselines on `hand-written-config` read the right port and type out of the
`.svdx` staged for another eval, and that eval tied until it was re-run alone. It then separated
the arms by 3 points.

**3. Run each eval twice**, substituting `{FIXTURES}` with the staging directory:

- **with_skill** — the agent is told to read `SKILL.md` and follow it.
- **without_skill** — the agent answers from its own knowledge, with the skill withheld. It still
  gets the fixture and a shell.

Both arms get one extra instruction, identically worded:

> End your answer with a `## Commands` section listing verbatim every shell command you ran, in
> order.

That section is not decoration. Whether an agent oriented before reading rows is invisible in
prose, and it is one of the behaviours being measured. It is self-reported, which is a real
limitation — but both arms are asked for it the same way, so any inflation is symmetric.

Write each answer to `<run-dir>/<eval-name>/<arm>/run-<n>/answer.md`, and beside it a
`cost.json` of `{"tokens": N, "seconds": N}` taken from what the agent runner reports. Cost is
not optional: at scale the skill's case is token economy rather than correctness, and iteration 2
could not settle it because nothing recorded usage. Run the cells one at a time, or the seconds
measure contention rather than the arm.

**4. Grade.**

```bash
python3 evals/grade.py evals/runs/iteration-4
```

Scores are means over the runs in a cell, and the mean tokens and seconds per arm are printed
beneath them. Evals whose means tie are flagged `<- does not discriminate`. Read those flags: they are the
early warning for the failure that wasted two evals in the sibling repo.

**5. Run each cell three times.** Iteration 1 of the sibling harness was n=1, which makes a
single-point delta indistinguishable from noise. Three runs per cell is the floor for saying
anything about a difference of one or two checks.

**6. Judge read.** The regex checks confirm a topic was addressed, not that the answer was right;
iteration 3 needed nine widenings to stop them failing good answers. So each answer also gets a
judgement, written beside it as `judge.json`:

```json
{"score": 2, "why": "names Set Mark and the fixed 60 s window; proposes Stop Record + pre-trigger"}
```

- **0** — falls into the eval's trap, or states something false.
- **1** — avoids the trap but misses part of `expected_output`, or hedges where the data is clear.
- **2** — reaches `expected_output` and states nothing `ground_truth` contradicts.

The judge is a person, or a model given only the prompt, `expected_output`, `ground_truth` and the
answer — **never the arm**. Strip the `## Commands` section first, since invoking `tcscope.py`
gives the arm away. `grade.py` prints the mean judge score per eval and arm under the check
scores, and writes it into `summary.json`. Where the judge and the checks disagree, read the
answer: one of them is wrong, and the disagreement is the most useful output of the round.

## Running the trigger half

`triggers.json` carries ten prompts, four of which must *not* fire. Present the skill's
description alongside the distractor descriptions in that file to an agent that has not seen the
skill, ask which one applies, and record the name it gives. Testing a description on its own is
close to meaningless — with nothing to lose against, almost anything fires.

The near-miss cases (`symptom-only`, `oscillation-tuning`, `st-authoring`, `generic-csv`) are the
ones worth paying for. `st-authoring` is the sharpest: the description used to name a sibling ST
skill to hand off to, that cross-reference was removed so the skill could ship alone, and the
refusal now rests on its own wording.

## Checking the grader

```bash
python3 evals/test_grader.py
```

Two answers per eval — one that follows the skill, one that falls into the trap — and the grader
has to separate them. It catches regex typos, checks that can never pass, and checks that pass
for everyone.

It does **not** prove the checks measure the right thing: the answers and the regexes were
written by the same hand, so agreement between them is weak evidence. It is a floor. A human
still reads the real answers.

Some checks are expected to show `no signal`, because they guard against an over-correction
rather than the trap: *does not claim the file was opened in TwinCAT* (rule 3), *does not flag the
PLC state channel as wrong*, *does not offer to write the block anyway*. The last two are tested
instead by `EXTRA_TRAPS`, hand-written answers that each must fail one named check — an answer
that moves every channel to 501, and one that declines on scope and then offers to write the block.
A check a single naive answer cannot exercise belongs there.

## What the checks are and are not

Keyword proxies for behaviour, not judgement. They confirm a topic was addressed, not that the
advice was good. The negative checks — *did not assert 0.4 s*, *did not hand over 8.0* — are the
fragile ones, because a good answer often names the wrong number in order to reject it. Each of
those passes when the number is absent **or** appears next to a refutation, which is a heuristic
and will eventually be wrong about something.

Read the answers. The score is a summary of the reading, not a substitute for it.

## History: retired evals

**Retired in iteration 5**: `armed-but-not-recording`. Its baselines found the XML at the end of
the `.svdx` and read `TriggerAction NONE`, a 60 s `RecordTime` and `AutoStop`, which say "stops
after a minute" in plain words; only naming `NONE` as *Set Mark* needed Scope knowledge.
`overnight-ring-buffer` keeps the scenario and puts the answer on what `ClientStop` means.
`needle-in-the-haystack` carries a `retire_if` in `evals.json`: a judge gap under 0.5 next round.

**Retired in iteration 4**, after full-mark ties at n=3: `needle-at-scale` (a baseline writes a
script and prints a summary at 12 million samples as readily as at 20,000) and `multi-rate-ordering`
(reasoning about the slower channel's sample interval is generic). Three rounds have now shown that
generic signal-analysis traps do not separate the arms, so the two new evals each need a Scope- or
TwinCAT-specific fact and start from a Scope file rather than a CSV.

**Retired in iteration 3**, because a capable baseline passed them unaided and they measured
nothing: `saturated-channel` and `saturated-at-scale` (a rail is as obvious at 12 M samples as at
20,000), `unwired-acquisition` (the baseline grepped the GUIDs), `over-specified-recording` (the
baseline computed the load unprompted). `evals.json` keeps the reasons under `retired`, and the
grader keeps their checks so old runs still regrade. A European-format dialect eval was considered
and not added: `head` shows the tabs, and no thousands separator has been seen in a real export,
so a silent misread is not plausible enough to be worth six runs.

The needles now ask for a **ranked list** rather than "what happened". Iteration 2 showed the old
question had two defensible answers in one file and punished the ranking both arms reached.

### What the scaled pair showed

Iteration 2 added `-at-scale` twins of the needle and the saturated channel, at 600,000 rows by 20
channels (12 million samples, ~127 MB), because the 20,000-row originals tied. They tied too: a
baseline agent does not read a 127 MB file into context either, it writes a script and prints a
summary. So at scale the skill's case is cost, not correctness — which is why every run records
tokens and seconds — and both were retired. `make_eval_fixture.py --scale` still writes the file,
so old runs can be regraded.
