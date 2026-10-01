# Eval results — iteration 6: two file-proof evals, and a skill answer the judge turned over

Iteration 5 retired two evals whose answers could be decoded from the file itself and asked for
replacements that no field of the file states. This round has them — `export-batch-script` and
`scaled-export` — and `tc2-port-config` carries on the port-801 half of the retired
`second-site-config`. Both new evals separate the arms on the checks. On one of them the judge
reverses the checks, and the judge is right.

Run 2026-10-01. **n = 3 per cell**, 7 evals × 2 arms, 42 runs, no re-runs.

## Setup

| | |
|---|---|
| Commit | `main` at `47373cb` (PR #63). `SKILL.md`, `references/`, `scripts/` and `templates/` staged with `git archive HEAD` |
| Model | `claude-opus-5-5` (Opus 5.5), both arms, default settings |
| Runner | One fresh Agent-tool subagent per run. **New:** each prompt sat alone in a randomly named folder inside an unlistable directory and the agent was given only its path, so no agent could list another's prompt and the orchestrator did not read which arm a run was until grading |
| Staging | `stage_runs.py stage --runs 3 --seed 6` into `/tmp`: one directory per run, `data/` plus `skill/` for the skill arm. uv pre-warmed. The id-to-arm map was kept outside the stage until grading |
| Pairing | Three rounds of 14 in parallel. Tokens are unaffected; **seconds are measured under contention** |
| Judge | One fresh subagent per eval, given the eval's prompt, `expected_output`, `ground_truth` (the eval's text and `ground_truth.json`) and the six answers shuffled as A–F, `## Commands` stripped, the tool's name, the skill's paths and the word "skill" replaced. Verb names and method still show in prose; that limit stands |

**A harness artefact, reported because it touched both arms.** The runs were started from a
session isolated in a git worktree, and its guard refuses any shell command it cannot parse
("too complex to verify"). Subagents inherit it. It refused 17 commands across 15 skill runs and
15 across 13 baseline runs — close to symmetric. What each refusal cost its run was not
measured. Three baseline runs wrote their answer with one refused heredoc and reported "written"
without seeing the refusal; those three answers were recovered from the refused command, byte
for byte. Next round: run from a session that is not worktree-isolated.

## Score

Mean of three runs, per-run check scores in brackets. No widening this round.

| Eval | With skill | Baseline | Δ | Judge (skill / baseline) |
|---|---|---|---|---|
| `hand-written-config` | 5.0/5 [5 5 5] | 2.7/5 [2 2 4] | **+2.3** | 2.00 / 0.67 |
| `export-batch-script` *(new)* | 5.0/5 [5 5 5] | 2.7/5 [3 3 2] | **+2.3** | 2.00 / 0.67 |
| `scaled-export` *(new)* | 3.7/5 [4 3 4] | 1.3/5 [2 1 1] | **+2.3** | **0.00 / 1.00** |
| `out-of-scope-authoring` | 3.7/5 [3 4 4] | 2.3/5 [3 3 1] | **+1.3** | 2.00 / 0.00 |
| `broken-cross-group` | 5.7/6 [6 6 5] | 4.7/6 [5 4 5] | **+1.0** | 2.00 / 0.33 |
| `tc2-port-config` | 5.0/5 [5 5 5] | 4.0/5 [4 4 4] | **+1.0** | 2.00 / 1.00 |
| `needle-in-the-haystack` | 7.0/7 [7 7 7] | 7.0/7 [7 7 7] | **0** | 1.67 / 1.00 |
| **Total** | **35.0/38** | **24.7/38** | **+10.3** | 1.67 / 0.67 |

Pass rate 92 % against 65 %. The judge ranks the skill arm ahead on six of seven evals and
behind on one.

## What each eval showed

**`scaled-export` — the skill arm fell into the trap, three times out of three.** The file's
torque peaks at about 79, with `ScaleFactor` 2 and `Offset` 10 in the header, and nothing in it
says whether Scope View applied that scaling on export. The expected answer is that the file
cannot settle whether torque passed 150 %: 79 if the values are already scaled, about 168 if
they are raw. Every skill run opened with a confident "No". Their reasoning was the same each
time and came from the skill: `manifest` calls it *display scaling* and tells the reader to get
back to raw values, so the runs took raw as the real torque — 79 if the export was raw, 34.5 if
it was scaled — and called multiplying 79 up to 168 "wrong in both cases". All three baselines
said the file does not settle it and gave both 79 and 168; none named the export option that
decides it, so they scored 1. **The skill's wording caused a wrong confident answer where the
unaided model was properly unsure.** The scaling exists so the chart shows the unit the engineer
reads, and the file does not say which of raw and scaled that is; the skill has to say so.

**`export-batch-script` — the clearest separation among the new ones.** Skill 3/3 name all
three silent failures — no `silent`, `,` where `channellist=` needs `;`, milliseconds where
`start=`/`end=` need absolute FILETIME ticks — and that each exits 0, and give a corrected line.
No baseline named the separator or the tick range; one listed the millisecond arithmetic as
fine and kept it in its suggested line (judge 0).

**`hand-written-config` — as in iterations 4 and 5.** Skill 3/3 moved the axis channels to 501
and typed them `REAL64`. Baselines hedged on the port ("probably") and one listed "LREAL with
size 8 is consistent" among the things that are fine.

**`out-of-scope-authoring` — the pattern holds, the check does not.** All three baselines wrote
the function block; no skill run did. The judge gives the skill arm 2.00, and the check
"declines to author the FB, and gives scope as the reason" failed on all three skill runs that
did exactly that. A grader miss, listed below.

**`broken-cross-group` — as before.** Skill 3/3 refuse either ordering and ask for a re-export.
Two baselines assert an order from the file; one declines for a weaker reason.

**`tc2-port-config` — a smaller gap, and a real one.** Every run found 801 → 851. The skill
runs said flatly that no TwinCAT 3 runtime answers on 801; every baseline hedged with "unless
the target really is TwinCAT 2" and promoted the placeholder NetID to a must-fix.

**`needle-in-the-haystack` — tied on checks a sixth time, kept by its own rule.** All six runs
found and ranked the four planted defects. The judge separates them on one point: four of six
listed the axis's normal standstill creep as a fifth thing wrong (three baselines, one skill
run). Judge gap 0.67; its `retire_if` fires below 0.5, so it stays one more round.

## Where the checks and the judge disagree

- **`scaled-export`: checks +2.3 for the skill, judge 0.00 against 1.00.** Four of the five
  checks are keyword checks — both figures mentioned, the header, the option named, a way to
  settle it — and a run can pass all four while answering "No". Only the fifth, *neither backs
  nor rules out the bigger drive*, tests the conclusion, and it failed on all three skill runs.
  The judge read the conclusion. **The judge is right and the check total is wrong here.**
- **`out-of-scope-authoring`:** the scope-reason and hand-off checks fail on skill answers the
  judge scores 2. The regexes miss the wording these runs used.
- **`needle-in-the-haystack`:** the checks cannot see a normal behaviour reported as a defect.

Taking the judge as the measure, the round reads: skill ahead on six, behind on one, and the one
is a defect in the skill.

## Cost

| Arm | Mean tokens | Mean seconds (under contention) |
|---|---|---|
| With skill | 78 869 | 81 |
| Baseline | 66 724 | 83 |

The skill arm spends about 18 % more tokens, most of it reading `SKILL.md` and a reference, and
takes no longer.

## Decisions

- **Fix the scaling wording in the skill** (`manifest`'s warning, `references/export-tool.md`,
  `SKILL.md`): a channel's scale factor and offset may be the conversion to the unit the reader
  wants, the file says neither whether it was applied nor which value is the physical one, and
  the answer is both readings until the export setting is known. Then re-run the skill arm of
  `scaled-export`.
- **Keep `needle-in-the-haystack`** one more round, by its own rule.
- **Keep both new evals.** `export-batch-script` separates the arms on checks and judge alike;
  `scaled-export` found a defect on its first outing.

## Re-run after the fix

The scaling wording was changed in PR #65 (`f72de0f`): `manifest`'s warning,
`references/export-tool.md` and `SKILL.md` ask for both readings until the export setting is
known, and no longer call it display scaling. The skill arm of `scaled-export` was then run again,
n = 3, staged the same way from that commit, and judged by a fresh blinded subagent beside the
three baseline answers from the main round.

| `scaled-export` | Checks | Judge |
|---|---|---|
| With skill, main round (`47373cb`) | 3.7/5 [4 3 4] | 0.00 |
| With skill, after the fix (`f72de0f`) | **5.0/5 [5 5 5]** | **2.00** |
| Baseline (same three answers both times) | 1.3/5 [2 1 1] | 1.00, then 0.67 |

All three re-runs open by saying the export cannot settle it, give 79 and 168, name the export
setting and ask for it or the `.svdx`. With that cell replaced the round totals 36.3/38 against
24.7/38, and the judge ranks the skill arm ahead on all seven evals.

Two cautions. The second judge scored one baseline answer 0 where the first gave it 1, on
identical text: a judge's score on a hedged answer moves by a point between reads, so a gap of
one point on one run is not a finding. And the re-run is three runs of one cell against text
written to fix it; iteration 7 has to show it holds beside the other evals.

## Changes before iteration 7

- `scaled-export`: add a check that fails a flat yes or no, so the check total cannot pass a
  trapped answer.
- `out-of-scope-authoring`: widen the scope-reason and hand-off checks to the wording these
  runs used.
- Run from a session that is not worktree-isolated, or the guard's refusals join the
  measurement again.

**Done, in the iteration 7 prep.** The checks were changed as listed, `needle-in-the-haystack`
gained a check for normal creep listed as a defect, and `stage_runs.py` now hides each prompt,
keeps the arm map outside the stage, refuses to collect a round with a missing answer, and
stages and files the judge read. The same 42 answers regraded with the new checks, so that a
later `grade.py` run on them is not read as a different result:

| Eval | Above | Regraded (skill / baseline) | Judge (skill / baseline) |
|---|---|---|---|
| `scaled-export`, main round | 3.7/5 vs 1.3/5 | **0.0/6 vs 2.3/6** | 0.00 / 1.00 |
| `scaled-export`, skill arm after the fix | 5.0/5 | 6.0/6 | 2.00 |
| `out-of-scope-authoring` | 3.7/5 vs 2.3/5 | 5.0/5 vs 2.3/5 | 2.00 / 0.00 |
| `needle-in-the-haystack` | 7.0/7 vs 7.0/7 | 7.7/8 vs 7.0/8 | 1.67 / 1.00 |
| **Total, main round** | 35.0/38 vs 24.7/38 | 33.3/40 vs 25.7/40 | |

On these three evals the regraded checks now order every run as the judge did.
