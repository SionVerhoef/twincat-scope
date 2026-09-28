# Eval results — iteration 4: Scope-specific evals, isolated stages, and a judge

Iteration 3 ended with two full-mark ties and a conclusion: generic signal-analysis traps do not
separate the arms. This round retires those two, adds two evals that start from a Scope file and
need a Scope fact, makes the needle fixture realistic, and adds a blinded judge beside the regex
checks.

Run 2026-09-28. **n = 3 per cell**, 5 evals × 2 arms, plus 12 re-runs (see *Staging*).

## Setup

| | |
|---|---|
| Commit | `main` at `c137eb9` (PR #34). `SKILL.md`, `references/`, `scripts/` and `templates/` staged with `git archive HEAD` |
| Model | `claude-opus-5-5` (Opus 5.5), both arms, default settings |
| Runner | One fresh Agent-tool subagent per run, as in iteration 3 (`claude -p` stays refused by the session's auto-mode classifier). Each wrote its answer to a file named only by a neutral run id, so no answer passed through the orchestrator |
| Staging | One directory per run under `/tmp`, neutral ids, `data/` plus `skill/` for the skill arm only. uv pre-warmed. `ground_truth.json` never staged |
| Pairing | Each round's 10 runs in parallel. Tokens are unaffected; **seconds are measured under contention** and are not comparable with iteration 3 |
| Prompts | `evals.json` exactly, plus the same lines for both arms: work from the stage, do not read `/projects` or `~/.claude`, no notifications, end with `## Commands`, write the answer to the given file |
| Judge | One fresh subagent per eval, given the prompt, `expected_output`, `ground_truth` and the six answers shuffled as A–F with `## Commands` stripped. Scores 0–2 per README *Judge read* |

## Staging: the first run was contaminated

The first 30 runs shared one `data/` holding all four live fixtures, as iteration 3 had.
Agents list the folder and read what is in it, and 11 of the 24 file-based answers used another
eval's file. It mattered on two evals:

- **`hand-written-config`.** Baselines took `REAL64` from the project inside the `.svdx` staged
  for `armed-but-not-recording` ("Both exports in the folder list 8-byte floats as `REAL64`").
  The eval tied at 4.3 vs 4.3.
- **`armed-but-not-recording`.** Agents in both arms searched the other recordings for the jam.

Both were re-run, all 12 cells, each stage holding only that eval's own file. Their scores below
are the re-runs; the shared-stage runs are kept beside them (`runs/iteration-4-shared-stage`).
`broken-cross-group` and `needle-in-the-haystack` answers mention other files only in passing
(three of twelve) and were not re-run. The README now says: stage every eval on its own.

Isolated, `hand-written-config` went from a tie to the widest gap of the round: all three
baselines called the file "sound", accepted `LREAL` as "8 bytes, matches", and never mentioned
port 501.

## Score

Mean of three runs, per-run scores in brackets. **After widening** (see below):

| Eval | With skill | Baseline | Δ | Judge (skill / baseline) |
|---|---|---|---|---|
| `hand-written-config` | 5.0/5 [5 5 5] | 2.0/5 [2 2 2] | **+3.0** | 2.00 / 0.00 |
| `broken-cross-group` | 6.0/6 [6 6 6] | 4.0/6 [3 4 5] | **+2.0** | 2.00 / 0.67 |
| `out-of-scope-authoring` | 4.3/5 [5 4 4] | 2.3/5 [2 2 3] | **+2.0** | 1.67 / 0.00 |
| `armed-but-not-recording` | 6.0/6 [6 6 6] | 5.3/6 [5 5 6] | +0.7 | 2.00 / 1.00 |
| `needle-in-the-haystack` | 7.0/7 [7 7 7] | 7.0/7 [7 7 7] | **0** | 2.00 / 1.33 |
| **Total** | **28.3/29** | **20.7/29** | **+7.7** | |

**Before widening**, on the same answers: 25.7 vs 20.7 (+5.0). Unlike iteration 3, every point
the widening moved went to the skill arm; the baseline's total did not change. That is the
direction to distrust, so each change is listed with the answer that prompted it, and the
judge — who never saw the checks — is the cross-check: it ranks the arms the same way on all five
evals.

## Widening

Every change applies to both arms, and `test_grader.py` still separates good from trapped
answers on every eval, extra traps included.

- **Declines on scope.** All three skill answers wrote "writing the ST is outside what this skill
  does"; the check knew only "outside (of) scope". Added `outside (of) what (this|the|my)`.
- **Offers to write it anyway — made stricter.** One skill answer ended "If you'd rather have the
  ramp FB tonight anyway, say so… It's your decision." That is an offer, and the check missed it.
  It now fails that answer, which costs the skill arm a point.
- **Hands the work over.** "hand the fix over" now counts, as "hand it over" did.
- **Refutes 0.4 s.** "…falls at about 0.4 s, and the order flips. With this file, the order
  depends on which clock you believe." `refuted()` now knows `doesn't` and `depends on which`.
- **Per-group clock.** "t = 0.800 s on its own clock", "runs on its own stretched clock".
- **Clipped velocity.** "ActVelo is cut off at exactly ±8.0, 55 % of the time": added `cut off
  at`, `cap(ped)`, `plateau`.
- **Guard: does not flag the PLC channel.** It fired on "`nState` on 851 is correct. 2. **Wrong
  type**…" — an 80-character window across two sentences. It now needs one sentence and a claim.

The baseline failures were read the same way and left standing. On `broken-cross-group` the
baselines see that the groups have their own time columns and decline to order the events, but
none says the slow group was never padded or asks for a re-export — the finding the check exists
for.

## What each eval showed

**`hand-written-config` — the skill's clearest win.** Every skill run ran `checkscope`, found both
faults on all three axis channels, said `nState` on 851 is correct, and gave the fix. Every
isolated baseline read the XML carefully — GUIDs, charts, sample time — and passed both faults.
All three raised the placeholder NetId instead, and wondered whether the symbol paths need
`NcToPlc`. A generalist knows what LREAL is and what port the PLC is on; what it does not know is
that Scope wants its own type names and that NC symbols live on 501.

**`broken-cross-group` — as in iteration 3.** Skill 3/3 name the unpadded group and the 1998 ms
disagreement; baselines refuse the ordering for weaker reasons ("no common time base"), and one
leans toward an order anyway (judge 0).

**`out-of-scope-authoring` — the new staging fixed it.** With an empty `data/`, no run in either
arm went hunting through other recordings. All three baselines wrote the complete function block
for tonight's paste, with caveats; no skill run did. One skill run then offered to write it after
all, and loses that check.

**`armed-but-not-recording` — weaker than designed.** The baselines found the XML at the end of
the `.svdx` on their own, read `TriggerAction NONE`, `RecordTime` 60 s and `AutoStop`, concluded
the file stops after a minute, and proposed a Stop Record trigger with a pre-trigger. What they
missed is only that `NONE` is Scope View's *Set Mark* — the judge's 1 against 2. A `.svdx` ends in
plain XML, so reading it is not Scope knowledge. The fixture also gives a second route: its
`ChannelTriggerSet` is empty (the channel condition was left out of the generated group), and one
baseline concluded "no channel and no threshold" from that.

**`needle-in-the-haystack` — ties on the checks, not on the judge.** All six runs found all four
planted defects with times. The judge preferred the skill arm (2.00 vs 1.33): two baselines
ranked routine motion — ActPos drifting a few hundredths — among the findings. The messier fixture
did its job for realism and did not create a gap the checks can see.

## Cost

| | With skill | Baseline |
|---|---|---|
| Mean tokens per run | 76,228 | 69,927 |
| Mean tool calls | 10.6 | 9.4 |

The skill arm costs **9 % more tokens** overall, most on `needle-in-the-haystack` (91.8k vs 79.4k)
and `broken-cross-group` (76.8k vs 62.8k); on `hand-written-config` and `armed-but-not-recording`
the two arms cost the same. These are the runner's total subagent tokens per run, not
iteration 3's cache-read breakdown, so the two rounds' cost figures are not comparable. Seconds
were measured under contention and are not reported.

## Changes before iteration 5

1. **Stage every eval alone** — done in the README this round. Make `make_eval_fixture.py`
   write one directory per eval so it cannot be got wrong.
2. **Harden `armed-but-not-recording`.** Put a real channel condition in the `ChannelTriggerSet`
   so "no channel" is not a second route, and make the Scope fact carry the answer: an action the
   XML does not explain by its name, or a restart flag whose effect is Scope-specific.
3. **Retire or rework `needle-in-the-haystack`.** Four rounds of ties on the checks. Keep it only
   if the judge's gap holds; otherwise it costs six runs for no signal.
4. **Add another configuration eval like `hand-written-config`** — the pattern that separates the
   arms is a file that looks right to anyone who knows the PLC side. Candidates from the field
   history: a display channel whose acquisition is on the wrong port, a sample time the task
   cannot deliver.
5. **Keep the judge.** It agreed with the checks on direction everywhere and caught what they
   cannot (an answer leaning toward an order it said it could not confirm; routine motion ranked
   as a finding).
