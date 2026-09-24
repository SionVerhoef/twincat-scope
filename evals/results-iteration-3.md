# Eval results — iteration 3: three runs per cell, and the first cost measurement

Iteration 2 left two questions open: does the skill change the answer once a cell is run often
enough to trust the difference, and what does it cost? This round runs five evals × two arms ×
three runs against the SKILL.md that shipped in PR #24, and records tokens and seconds for every
run.

Run 2026-09-23. **n = 3 per cell**, which is the README's floor for calling a difference real.

## Setup

| | |
|---|---|
| Commit | `7cb780c` on `worktree-bnb-evals-round2`, which is main at `e73d470` (PR #24) merged in. The staged `tcscope.py` is the branch's copy, i.e. main plus the cross-group skew note, not bare main |
| Model | `claude-opus-5-5` (Opus 5.5), both arms, default settings |
| Runner | One fresh Agent-tool subagent per run, never reused. `claude -p --output-format json` was the first choice, because it reports a full usage breakdown and runs from its own directory, but the session's auto-mode classifier refused to launch headless agents with permissions bypassed, so the fallback the brief allows was used |
| Staging | `/tmp/evalstage/data` (all five fixtures) and `/tmp/evalstage/skill` (`git archive HEAD SKILL.md references scripts templates`). `ground_truth.json` was never staged. uv was pre-warmed (`tcscope.py doctor`, `uv run --with pandas,numpy`) before the first measured run |
| Pairing | Each batch ran one eval's two arms concurrently; the 15 batches ran one after another. Eval order was shuffled by hand each round (`runs/iteration-3/batch-order.json`). The stage was reset to `data/` + `skill/` between batches |
| Fixtures | `make_eval_fixture.py --scale`; `manifest` on `press_line_export.csv` reports `cross_group_timing_valid: true` and "disagree by up to 9 ms", which `multi-rate-ordering` depends on |

Prompts were the brief's exactly, with two identical additions to both arms. First, "Work from
/tmp/evalstage (cd there before any command)", because a subagent starts in the session's working
directory rather than in the stage. The brief's "Do not read anything under <repository checkout>"
line is what keeps the answer key out of reach. Second, "Do not send any notifications", because
subagents inherit a global instruction to send push notifications on completion. No answer reports
reading the repository, and no baseline reports reading `skill/`.

## Score

Mean of three runs, per-run scores in brackets. **After widening:**

| Eval | With skill | Baseline | Δ |
|---|---|---|---|
| `broken-cross-group` | 6.0/6 [6 6 6] | 3.3/6 [4 3 3] | **+2.7** |
| `out-of-scope-authoring` | 3.7/4 [4 3 4] | 2.7/4 [3 2 3] | +1.0 |
| `needle-in-the-haystack` | 7.0/7 [7 7 7] | 6.7/7 [6 7 7] | +0.3 |
| `needle-at-scale` | 7.0/7 [7 7 7] | 7.0/7 [7 7 7] | **0** |
| `multi-rate-ordering` | 6.0/6 [6 6 6] | 6.0/6 [6 6 6] | **0** |
| **Total** | **29.7/30** | **25.7/30** | +4.0 |

**Before widening** the table read 28.0 vs 20.7 (+7.3): `broken-cross-group` 6.0 vs 2.3,
`needle-in-the-haystack` 7.0 vs 6.3, `needle-at-scale` 7.0 vs 6.3, `out-of-scope-authoring` 2.7 vs
1.3, `multi-rate-ordering` 5.3 vs 4.3. Widening closed three points of the gap, which is the
direction that matters: every change was made after reading answers, and each one made the
baseline look better, not worse.

Nine checks were widened. All but one are vocabulary gaps where a correct answer was marked wrong
for its phrasing. Every change applies to both arms, and `test_grader.py` still reports "grader
separates good from trapped answers on every eval" afterwards.

- **`asserts()` negations** now know `doesn't / didn't / isn't / wasn't / wouldn't`. "That doesn't
  show the following error came first" was being scored as claiming it.
- **Torque-came-first**: "The torque spike *first shows* at t=410" matched `spike … first`. That
  pattern now ignores "first shows / appears / seen".
- **Drive purchase**: "I wouldn't order a drive on the strength of it", given by all three
  baselines, missed because `wouldn't` does not contain `not`.
- **Does not clear the drive**: "so it doesn't clear the drive", "Hold off on sending the mechanics
  in", "has no support here".
- **Declines to author**: all six answers, in both arms, open with "I haven't written the ramp
  function block."
- **Offers the measurement half**: "For the next recording, add…", "Record the drive/NC error ID…".
- **Spike width**: "a 3-sample spike" (hyphen).
- **`needle-at-scale` times**: one baseline gave only wall-clock times derived from the file's
  `StartTime`, 06:06:53.776 and 06:04:51.004–06:04:53.517. These are the right events at the right
  instants, in a format the pattern did not know.

Checks left failing on purpose, because they are real misses: a baseline that called the clipped
velocity "a flat ±8 that doesn't match position" without ever saying it saturates; baselines that
never identify the clamp export as broken; baselines that recommend re-recording rather than
re-exporting; and authoring answers that decline but point the work nowhere.

## Cost

This is the first round with cost recorded. `tokens` is the subagent notice's `subagent_tokens`,
which behaves as the agent's context size at the end of the run rather than a running sum.
`cache_read` is summed per API call from the agent's transcript. The transcript's output-token
figures are unreliable (some runs show under 100 for multi-kilobyte answers) and are not used.

| Eval | Tokens, skill | Tokens, baseline | Cache read, skill | Cache read, baseline | Median s, skill | Median s, baseline |
|---|---|---|---|---|---|---|
| `broken-cross-group` | 70,955 | 60,203 | 503k | 242k | 67 | 80 |
| `needle-in-the-haystack` | 84,194 | 71,892 | 714k | 456k | 134 | 144 |
| `needle-at-scale` | 103,068 | 70,810 | 1,086k | 622k | 208 | 165 |
| `out-of-scope-authoring` | 89,513 | 67,430 | 986k | 438k | 198 | 131 |
| `multi-rate-ordering` | 74,338 | 68,073 | 609k | 413k | 86 | 133 |
| **All 15 runs** | **84,413** | **67,682** | **780k** | **434k** | 132 | 133 |

Spread is tight: within a cell, no two runs differ by more than 11% in tokens.

**The skill arm costs more on every eval.** Overall it takes 25% more end-of-run context and 1.8×
the cache reads. Every agent here starts from a fixed base of about 49.6k tokens (system prompt
plus inherited instructions); the trigger agents, which use no tools, all land at 49.6–50.0k. Net of
that base, the skill arm's task-specific context is about 35k tokens against the baseline's 18k:
**roughly twice the marginal cost.** The largest gap is `needle-at-scale`, +32k. That is the eval
SKILL.md's opening argument claims the skill is cheapest on.

Where the extra goes: the skill arm reads `SKILL.md` and usually `references/data-triage.md`, calls
`--help` on three or four verbs, and receives JSON from `stats` and `events` that is larger than a
hand-written summary. The baseline writes two to five compact pandas scripts and prints only what
it asked for. The skill arm also makes more tool calls on every eval: 9.7 against 4.3 on the clamp
export, 16.3 against 12.3 at scale.

**Seconds** are comparable within a pair only. Medians are level overall (132 against 133). One
outlier sits in the skill arm and is kept, not dropped: `out-of-scope-authoring` run 3 recorded
**3,006 s**. That agent ran `correlate` directly on the 127 MB CSV without converting it to Parquet
first. The call hit the 120 s tool timeout and was moved to the background. A follow-up numpy
full-file load was then killed for running out of memory (exit 137), and the agent idled waiting on
the backgrounded job. Its token cost was normal (87k). This is a real tooling finding: nothing in
the skill stopped `correlate` from running unconverted on a file that size.

## What each eval showed

### `broken-cross-group` — the one clear, repeated difference

All three skill runs named the export as broken: the slow group was never repeat-padded, the clocks
disagree by up to 1998 ms, and `cross_group_timing_valid` is false. All three asked for a re-export
on one sample rate, or `ingest` on the original `.svdx`.

All three baselines also refused to confirm the order, so none walked into the trap the eval was
built around ("torque at 0.4 s, torque first"). But none of them diagnosed *why* the file can't
answer. They put it down to "separate clocks, nothing lines them up" and to torque and following
error sitting on different axes. They recommended re-recording, which is costlier than a re-export.
All three then offered the reading of each group on its own clock ("following error comes
200 ms *before* the torque spike") as a hint against the maintenance hypothesis, before hedging.
That reading is only valid if the clocks agree, which is exactly what is broken.

So the skill's contribution here is a correct diagnosis and the cheaper fix, not avoiding a wrong
yes. It shows up in every run.

### `needle-at-scale` and `needle-in-the-haystack` — coverage no longer differs

Round 2's one behavioural difference was that the baseline missed the frozen torque channel. **It
did not recur.** All three scaled baselines found all four planted defects: the 12-unit position
step at 128.431 s, the frozen torque from 291.004 to 293.517 s, the 3-sample following-error spike
at 413.776 s, and the ±8 velocity clip. Most also reconstructed the true velocity peak (78.5) from
position. At 20,000 rows, the only baseline miss in six runs was one answer that saw the flat ±8
velocity without calling it clipping.

Both arms ranked the uncorrected position step first in all twelve needle runs. The ranked-list
question fixed round 2's grading flaw: no check now punishes that reading.

**The scale hypothesis is now disproved for coverage too.** A capable baseline writing its own
pandas finds everything in 12 million samples, in about the same time and with fewer tokens. The
skill arm's scaled answers are longer and add a sensitivity re-scan of the clean axes, but that is
polish, not a finding the baseline lacked.

### `multi-rate-ordering` — the trap was never taken

The eval exists to catch a baseline confirming "error first, torque reacted" from a 5 ms gap between
a 1 ms and a 10 ms channel. **No baseline confirmed it (0/3).** All three worked out that the torque
last read normal at 0.400 s, so the spike lies somewhere in (0.400, 0.410], and that 0.405 falls
inside that window. Two went further than the skill arm on physics: torque spiking with flat
current, and PosDiff stepping while SetPos − ActPos stays smooth. The skill arm reached the same
conclusion in all three runs, citing the manifest's 9 ms skew note. Its `correlate` output ("torque
leads by 3 ms") was correctly discarded as inside the uncertainty.

### `out-of-scope-authoring` — both decline, for different reasons

No answer in either arm wrote the function block. **The difference is the reason for declining.**
All three skill runs say writing PLC code is outside what the skill does, and two of them hand the
work to whoever writes the project's ST. Every baseline declines
only because the diagnosis looks wrong, and offers to write the block anyway if asked ("If you
still want the ramp block, tell me. I'll write it"). The current check scores both as declining. The
assertion in `evals.json` asks for the scope reason, and only the "points elsewhere" check picks
this up.

This eval also has a staging flaw. The prompt names no file, but `/tmp/evalstage/data` holds every
fixture, so both arms turn a scope-boundary question into a hunt through recordings belonging to
other evals. That makes the eval the skill arm's most expensive run (986k cache reads) for a
question that needs no data at all.

## What still doesn't discriminate

- **`needle-at-scale`**: 7/7 against 7/7, three runs each. Round 2's coverage difference was noise
  at n=1.
- **`multi-rate-ordering`**: 6/6 against 6/6 after widening. The baseline does the sample-interval
  arithmetic unaided.
- **`needle-in-the-haystack`**: +0.3, a single vocabulary-level miss in one baseline run.

On correctness, the skill's measurable edge in iteration 3 comes down to one eval: knowing that a
Scope View CSV export with unpadded groups is broken and that a re-export fixes it. That is
domain knowledge a capable model does not have, which is the kind of thing a skill is for. Generic
anomaly-finding and sampling-rate reasoning are not.

## Triggers

**36/36 correct**, all verbatim in `runs/iteration-3/triggers.json`. Each run showed the
description alongside three distractors, unlabelled and shuffled, and asked "which applies, or
none". The two no-neighbour cases were run with the matching distractor removed. The description
was taken from the staged SKILL.md frontmatter at run time, and its bytes are identical before
PR #24, after it, and on main, so these results carry to the shipped skill.

- The six should-fire cases picked the skill 18/18, including the near misses `symptom-only` and
  `oscillation-tuning`. On oscillation, two of the three answers flagged the match as weak because
  nothing names TwinCAT or a recording.
- The four should-not cases went to the matching distractor 12/12. `st-authoring` still says
  "TwinCAT" and was not pulled.
- `other-vendor` and `generic-csv` with their neighbour removed: "none" 6/6. The description does
  not grab a Siemens trace request or plain CSV work when nothing better is offered.

The trigger half discriminates nothing either. It passed 10/10 in iteration 1 and 36/36 now.

## Changes before iteration 4

1. **Retire `needle-at-scale` and `multi-rate-ordering`.** Two full-mark ties at n=3. Keep the
   20,000-row needle only as a cheap regression check.
2. **Keep `broken-cross-group`, and build more evals like it.** Each new eval should need a Scope-
   or TwinCAT-specific fact a generalist lacks: padding semantics, `BaseSampleTime` ticks,
   oversampling, and how Scope View exports multi-rate groups. Generic signal-analysis traps are
   now shown three times over not to separate the arms.
3. **Fix `out-of-scope-authoring`.** Stage it with an empty `data/`, and make "declines" require
   the scope reason. An answer that declines on the merits and offers to write the block anyway
   should not pass that check.
4. **Take "Synthetic scope export" out of the fixtures' preamble.** Several baselines, and one skill
   run, used it as evidence that the file might not be the real recording. That is a tell no real
   export carries.
5. **Treat the cost result as the headline, not a footnote.** The skill arm costs about twice the
   marginal tokens and wins on one eval. Either SKILL.md gets cheaper to follow (fewer `--help`
   round-trips, terser verb output, no reference read on questions that need none) or the pitch
   stops claiming token economy.
6. **Make the skill convert large files to Parquet before `correlate`.** The 3,006 s run is one
   `correlate` on a 127 MB CSV. The skill already advises Parquet for scanning; it should say so for
   every verb that loads a large file whole.
7. **Allow `claude -p` for the runner**, with a permission rule for this harness. It gives a real
   input/output/cache breakdown and a per-run working directory, which removes both prompt
   additions made this round.
