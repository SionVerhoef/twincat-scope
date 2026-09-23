# Evals — does the skill change the answer?

`tests/` measures the tool. This measures the *skill*: whether it fires on the right prompts,
and whether an agent reading `SKILL.md` reaches a different conclusion than one that never saw
it.

Two halves, different costs:

| Half | File | Asks | Cost |
|---|---|---|---|
| Behaviour | `evals.json` | Does the skill change the answer? | ~1 agent pair per eval, minutes each |
| Triggering | `triggers.json` | Does the description fire on the right prompts? | one short answer per case |

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
| `needle-in-the-haystack` | The glitch is 3 samples in 20,000. Any decimation that makes the file plottable steps over it. |
| `out-of-scope-authoring` | The diagnosis is done and the fix is obviously a few lines of ST. Writing it is the natural next move and the wrong one. |
| `needle-at-scale` | The same needle, in a haystack the size the skill's argument is about: 3 samples in 12 million, across 20 channels and 127 MB. |
| `multi-rate-ordering` | A valid export. Read as one table, the following error rises 5 ms before the torque. But torque is sampled every 10 ms, so the order is inside one of its samples and not in the data. |

**Retired in iteration 3**, because a capable baseline passed them unaided and they measured
nothing: `saturated-channel` and `saturated-at-scale` (a rail is as obvious at 12 M samples as at
20,000), `unwired-acquisition` (the baseline grepped the GUIDs), `over-specified-recording` (the
baseline computed the load unprompted). `evals.json` keeps the reasons under `retired`, and the
grader keeps their checks so old runs still regrade. A European-format dialect eval was considered
and not added: `head` shows the tabs, and no thousands separator has been seen in a real export,
so a silent misread is not plausible enough to be worth six runs.

The needles now ask for a **ranked list** rather than "what happened". Iteration 2 showed the old
question had two defensible answers in one file and punished the ranking both arms reached.

### Why two evals are run twice, at two sizes

`needle-in-the-haystack` and `saturated-channel` both scored 6/6 in *both* arms in iteration 1.
That is not evidence the skill adds nothing there — their fixture is 20,000 rows and 1 MB, a
haystack you can tip out onto the table. A baseline that loads the whole file and takes
`diff().abs().max()` finds a three-sample spike every time, and did.

The `-at-scale` pair is the same two traps against 600,000 rows by 20 channels — 12 million
samples, ~127 MB, the file SKILL.md's opening argument describes. The small pair is kept
because the comparison between the two sizes is itself the measurement.

**Expect the scores to stay level anyway.** A baseline agent does not read a 127 MB file into
context either: it writes a script and prints a summary, which is exactly what iteration 1's
baseline did. If the scaled pair also ties, that is a finding and not a failed eval — it means
the ladder's value is not correctness but token economy and consistency, and that is a *cost*
measurement. So record tokens and wall clock per arm, or the most likely outcome of the scale
test is uninterpretable.

## Running the behaviour half

**1. Build the fixtures.**

```bash
python3 evals/make_eval_fixture.py           # writes evals/fixtures/
python3 evals/make_eval_fixture.py --scale   # plus the 127 MB one, minutes to write
```

`--scale` adds `axis_run_20260904.csv`: 600,000 rows at 1 kHz across 20 channels, streamed a row
at a time because the point of it is a file too big to hold. Only Axis1 carries defects — a
three-sample following-error spike at 413.777 s, a position step at 128.431 s, a torque channel
frozen from 291.004 to 293.517 s, and a velocity channel clipped at ±8.0 while the motion under
it reaches 78.5. None of them sits on a round second, and all are inside the middle 80% of the
run, so head, tail and any coarse decimation step over them.

Regenerable and gitignored, like every other fixture in this repo. Ground truth is written to
`evals/ground_truth.json` — one directory *up* from the data, never beside it.

**2. Stage them somewhere neutral.** Copy `evals/fixtures/*` into a scratch directory outside the
repo and point the prompts at that. Two reasons: the file names in `tests/fixtures/` announce
themselves (`planted.csv` sitting next to `ground_truth.json` is not a measurement), and an agent
working inside the repo can read the answer key. The fixture names here are already neutral —
`clamp_station_export.csv`, not `skewed_export.csv` — but staging outside the repo is what makes
the baseline arm honest.

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
python3 evals/grade.py evals/runs/iteration-3
```

Scores are means over the runs in a cell, and the mean tokens and seconds per arm are printed
beneath them. Evals whose means tie are flagged `<- does not discriminate`. Read those flags: they are the
early warning for the failure that wasted two evals in the sibling repo.

**5. Run each cell three times.** Iteration 1 of the sibling harness was n=1, which makes a
single-point delta indistinguishable from noise. Three runs per cell is the floor for saying
anything about a difference of one or two checks.

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

One check is expected to show `no signal`: *does not claim the file was opened in TwinCAT*. It is
a guard against a specific dishonesty (rule 3) rather than a discriminator, and it should fire
rarely or never. It adds a constant to both arms; that is the price of keeping it.

## What the checks are and are not

Keyword proxies for behaviour, not judgement. They confirm a topic was addressed, not that the
advice was good. The negative checks — *did not assert 0.4 s*, *did not hand over 8.0* — are the
fragile ones, because a good answer often names the wrong number in order to reject it. Each of
those passes when the number is absent **or** appears next to a refutation, which is a heuristic
and will eventually be wrong about something.

Read the answers. The score is a summary of the reading, not a substitute for it.
