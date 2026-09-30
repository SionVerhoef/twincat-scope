# Eval results — iteration 5: two new Scope-file evals, and where they leak

Iteration 4 asked for two things: evals that start from a Scope file and need a Scope fact, and
a per-eval stage so no run can read another eval's file. This round has both. `armed-but-not-recording`
is retired and replaced by `overnight-ring-buffer`; `second-site-config` is new; `stage_runs.py`
stages every run alone under a neutral id.

Run 2026-09-29/30. **n = 3 per cell**, 6 evals × 2 arms, 36 runs, no re-runs.

## Setup

| | |
|---|---|
| Commit | `main` at `a6cf947` (PR #47, v1.0.0 prep). `SKILL.md`, `references/`, `scripts/` and `templates/` staged with `git archive HEAD` |
| Model | `claude-opus-5-5` (Opus 5.5), both arms, default settings |
| Runner | One fresh Agent-tool subagent per run, prompt inlined from `prompts/<id>.txt` so no agent could list the other prompts |
| Staging | `stage_runs.py stage --runs 3 --seed 5` into `/tmp`: one directory per run, `data/` plus `skill/` for the skill arm. uv pre-warmed. `map.json` read only after grading |
| Pairing | Three rounds of 12 in parallel. Tokens are unaffected; **seconds are measured under contention** |
| Judge | One fresh subagent per eval, given the eval's prompt, `expected_output`, `ground_truth` (both the eval's text and `ground_truth.json`) and the six answers shuffled as A–F, `## Commands` stripped. **New:** the tool's name was also replaced by `[tool]` in the answer bodies — on 23 lines, which in iteration 4 gave the arm away |

Each stage held only its own eval's file, so the iteration-4 contamination could not recur.

## Score

Mean of three runs, per-run check scores in brackets. **No widening this round** (see *Where the
checks and the judge disagree*).

| Eval | With skill | Baseline | Δ | Judge (skill / baseline) |
|---|---|---|---|---|
| `out-of-scope-authoring` | 5.0/5 [5 5 5] | 2.0/5 [1 2 3] | **+3.0** | 1.33 / 0.00 |
| `broken-cross-group` | 5.3/6 [6 6 4] | 3.7/6 [3 3 5] | **+1.7** | 2.00 / 0.67 |
| `hand-written-config` | 5.0/5 [5 5 5] | 3.7/5 [5 2 4] | **+1.3** | 2.00 / 0.00 |
| `second-site-config` *(new)* | 4.7/5 [5 5 4] | 4.3/5 [5 4 4] | +0.3 | 1.00 / 0.33 |
| `overnight-ring-buffer` *(new)* | 5.3/6 [6 6 4] | 5.3/6 [6 5 5] | **0** | 2.00 / 1.67 |
| `needle-in-the-haystack` | 7.0/7 [7 7 7] | 7.0/7 [7 7 7] | **0** | 1.00 / 0.33 |
| **Total** | **32.3/34** | **26.0/34** | **+6.3** | 1.56 / 0.50 |

The judge ranks the skill arm ahead on all six evals, as in iteration 4. The checks tie on two.

## What each eval showed

**`hand-written-config` — still the widest judge gap.** Skill 3/3 moved the three axis channels
to 501 and typed them `REAL64`, and left `nState` on 851 alone. All three baselines kept the axis
on 851 and proposed `NcToPlc` paths through an `AXIS_REF`; two got as far as "I'm fairly
confident, but not certain, that Scope expects REAL64". Judge 2.00 vs 0.00.

**`out-of-scope-authoring` — the pattern holds.** All three baselines wrote the function block.
No skill run did, and none offered to write it afterwards. Two skill runs lost a judge point for
not saying what to measure after the fix goes in.

**`broken-cross-group` — as in iterations 3 and 4.** Skill 3/3 name the unpadded group and the
1998 ms skew and ask for a re-export. Two baselines refuse the ordering for the weaker reason
("different time bases") and one leads with "the following error came first by 200 ms" — judge 0.

**`second-site-config` — the skill's own rule overreached.** All three skill runs and two of
three baselines found both faults, but:

- **The file teaches its own unit.** `RecordTime` 600000000 reads as 60 s only at 100 ns a tick,
  and the baselines used exactly that to confirm `BaseSampleTime` 1 is 100 ns. That half of the
  trap does not need Scope knowledge.
- **Port 801 did separate them.** One baseline listed the PLC channels on 801 under "what is
  correct"; one said NC data "normally sits under the NC server (port 500)"; one hedged "if it
  really is TC2, 801 is correct".
- **All three skill answers claimed Scope would round 100 ns up to the task cycle** ("in
  practice you would probably get the task rate"). The ground truth says this is unmeasured and
  must not be claimed. The source is `SKILL.md`: *"The sample time snaps to the task cycle."*
  That was measured for a sample time **above** one cycle (10 ms on a 4 ms task saved as 8 ms);
  the skill states it without the bound, and every skill run extrapolated it below one cycle.
  Judge 1.00 vs 0.33 — the skill arm ahead, but losing a point per run to its own reference.

**`overnight-ring-buffer` — does not discriminate.** Every baseline concluded the jam is not in
the file, and two of three said "the last 10 minutes before you pressed Stop". Two routes need
no Scope knowledge:

- **The byte count.** The sample block is exactly 12,000,000 bytes; four channels at 1 ms are
  19 bytes a sample, so ~10.5 minutes. All three baselines did this sum.
- **`RecordTime`** is 600 s in the file's own unit, as above.

What only the skill arm had was the name: `ClientStop` is Scope View's *Ringbuffer*, `NONE` is
*Set Mark*. That changes the vocabulary of the answer, not its conclusion. The empty
`ChannelTriggerSet` (iteration 4's second route) is still there, and two baselines used it.
Judge 2.00 vs 1.67.

**`needle-in-the-haystack` — every answer disagreed with `expected_output`, and they are right.**
All six runs ranked the 6.0 s `ActPos` step first, not the 12.0 s `PosDiff` spike. Their reason
is sound: a 12-unit offset at standstill that persists for the rest of the run, invisible to
`PosDiff`, so no alarm fired — that makes a bad part; a three-sample spike that recovers may not.
The judge docked every run a point for the ranking. With the ranking set aside, the gap comes
from two baselines that listed the normal `ActPos` drift as a fault (judge 0). The checks tie at
7/7 for the fifth round.

## Where the checks and the judge disagree

Read one by one. The judge was right each time.

- **`hand-written-config` baseline run-1: checks 5/5, judge 0.** It keeps the axis on 851 with
  `NcToPlc` paths, and mentions 501 once, as an aside ("record the NC axis directly, port 501").
  The 501 check matched the aside. **False positive** — the check needs to fail an answer that
  keeps the channels on 851.
- **`broken-cross-group` skill run-3: checks 4/6, judge 2.** It explains the row-for-row reading
  ("the torque spike comes *before* the following error") in order to reject it; `refuted()`
  missed the rejection two lines further down.
- **`overnight-ring-buffer` skill run-3: checks 4/6, judge 2.** "The jam at 03:12 … was
  overwritten long before you came in" failed *does not claim the jam is in the file*; "Stop
  Record … keep the ring buffer, the 600 s buffer then holds the 10 minutes leading up" failed
  for want of the word *pre-trigger*.
- **`second-site-config` skill run-3: checks 4/5.** "Not yet." is not in the *not ready* check.

Three of the four misses cost the skill arm; the one false positive helped the baseline. Widening
them now would move points only toward the skill arm, which iteration 4 said to distrust. They
are left as run and listed for the next round, each with its answer as a `test_grader.py` case.

## Cost

| Eval | Tokens skill / baseline | Tool calls skill / baseline |
|---|---|---|
| `needle-in-the-haystack` | 92.5k / 72.3k | 15.0 / 9.0 |
| `overnight-ring-buffer` | 81.2k / 71.3k | 12.7 / 12.0 |
| `hand-written-config` | 78.7k / 74.5k | 10.7 / 9.7 |
| `broken-cross-group` | 76.4k / 62.4k | 10.7 / 6.7 |
| `second-site-config` | 75.0k / 69.0k | 9.3 / 11.3 |
| `out-of-scope-authoring` | 66.4k / 53.5k | 7.0 / 4.0 |
| **Mean** | **78.4k / 67.2k (+17 %)** | **10.9 / 8.8** |

Iteration 4 measured +9 %. Most of the rise is reading `SKILL.md` on evals where the baseline
spends nothing: `out-of-scope-authoring` (+24 %) and `broken-cross-group` (+22 %). Seconds were
measured under contention: 96 vs 97 mean.

## Decisions

- **`needle-in-the-haystack` stays, by its own rule.** `retire_if` was a judge gap under 0.5; it
  is 0.67. But the gap rests on two baselines over-reporting drift, and the ranking the eval asks
  for is contestable. Rewrite `expected_output` to accept either the 6 s step or the 12 s spike
  first, if the reason given holds, and give it the same `retire_if` again.
- **`overnight-ring-buffer` should be retired.** Its answer follows from arithmetic on the file.
  A real `.svdx` would leak the same way — a ring buffer's file *is* the size of its window — so
  hardening the fixture would make it less realistic, not harder.
- **`second-site-config` should be reworked, not retired.** Drop the sample-time half, which the
  file teaches, and keep port 801, which separated the arms.

## Changes before iteration 6

1. **Fix the skill's snap rule.** `SKILL.md` and `references/scope-configuration.md` should bound
   it: measured for sample times above one task cycle; what Scope does below one cycle is
   unmeasured. Then `checkscope`'s own message should say the same.
2. **Fix the four check misses** above, each with the answer that exposed it added to
   `test_grader.py`, so the grader keeps separating good from trapped answers.
3. **Retire `overnight-ring-buffer`**, rework `second-site-config`, rewrite `needle`'s
   `expected_output`.
4. **New evals must not be decodable from the file itself.** The lesson of both new evals: if
   another field in the same file, the file's size, or an empty element gives the answer away, a
   careful generalist finds it. What separated the arms every round is a fact about TwinCAT or
   Scope that no field states — which port NC lives on, what type name Scope expects, that an
   export was never padded, that the skill does not write ST.
5. **Keep the `[tool]` redaction in the judge packets.**
