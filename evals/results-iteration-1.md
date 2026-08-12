# Eval results — iteration 1

Six prompts from `evals.json`, each run twice: once by an agent told to read and follow the
skill, once by an agent answering from its own knowledge with the skill withheld. Same model,
same fixtures, same shell, same working directory. Both arms were told `uv run --with
pandas,numpy` was available, so neither was handicapped on tooling. Graded mechanically against
33 objective checks.

Plus ten trigger cases from `triggers.json`, run against the skill's description alongside three
distractor descriptions.

Run 2026-08-12. **One run per cell** — single-point differences are noise, and the four zeros
below are the interesting part regardless.

## Score

| Eval | With skill | Baseline | Δ |
|---|---|---|---|
| broken-cross-group | 6/6 | 4/6 | **+2** |
| out-of-scope-authoring | 4/4 | 1/4 | **+3** |
| needle-in-the-haystack | 6/6 | 6/6 | **0** |
| saturated-channel | 6/6 | 6/6 | **0** |
| unwired-acquisition | 5/5 | 5/5 | **0** |
| over-specified-recording | 6/6 | 6/6 | **0** |
| **Total** | **33/33 (100%)** | **28/33 (85%)** | **+5** |

Triggering: **10/10**. Every fire case fired, every decline case went to the right neighbour —
including `st-authoring`, the case that matters most because the cross-reference naming a sibling
ST skill was removed so this skill could ship alone.

The headline number is not the result. **Four of six evals measured nothing**, and the entire
delta comes from two.

## Where the value actually is

**`out-of-scope-authoring` +3 — the clearest win.** Asked to write a ramp function block, the
baseline wrote it. A complete `FB_RampSetpoint`, under a heading reading *"## The block — here it
is"*, ready to paste into a production machine that night. The skill arm declined, said where the
work belonged, asked the four questions it would need answered first (NC or drive-internal, who
writes the setpoint, task cycle time, anything safety-rated), and offered the measurement half
instead. Scope discipline is doing real work here.

**`broken-cross-group` +2 — but not for the reason the eval was built.** The trap was that
reading the export as one table inverts cause and effect: the torque spike appears at 0.40 s,
before the following-error step at 0.60 s, when on its own group's clock it is at 0.80 s, after.

The baseline did not fall for it. It noticed the file had multiple time columns, declined to
confirm the maintenance hypothesis, never quoted the 0.4 s artefact, and told the user not to
order a drive on this evidence. What it could not do was say **why** — it never identified that
the slow group was never repeat-padded, and it never prescribed the fix. The skill arm named the
defect, quantified it (1998 ms of disagreement against a 2 ms sample time), laid both readings
side by side to show they contradict, and asked for a re-export.

So the win is diagnosis and prescription, not rescue from a wrong answer. Worth knowing, and
worth stating precisely, because "the skill stops you inverting cause and effect" is the claim I
would have made before running this, and the data does not support it.

## The four that measured nothing

This is the more useful half of the result.

- **`needle-in-the-haystack` 0.** The glitch is a three-sample spike in 20,000 rows and the
  baseline found it — at 11.999 s, correctly identified as ~3 samples wide — along with the 6 s
  position step, the 15–17 s torque flatline, the velocity clipping, and the sample rate. It
  never pasted bulk rows. It wrote seven analysis scripts and ran them.
- **`saturated-channel` 0.** Both arms refused to hand over 8.0. Both then recovered the real
  peak, 78.5, and agreed to three digits. The baseline did it three independent ways, including
  fitting a sine to the unclipped samples and an arcsin identity relating the clipped fraction to
  the amplitude — `1 − (2/π)·arcsin(C/A)` — which is a better piece of analysis than anything in
  `references/data-triage.md`.
- **`unwired-acquisition` 0.** The baseline grepped every `Guid` and `AcquisitionGUID`,
  cross-referenced them, found the dangling `deadbeef-…`, and gave two fixes. Then it went past
  the planted defect entirely: `RecordTime` is 60 s, which is a lottery ticket for an intermittent
  fault; position alone will not diagnose an axis stop; and `UseLocalServer: true` with a machine
  `AmsNetId` aims Scope at the laptop instead of the controller. `checkscope` finds none of those.
- **`over-specified-recording` 0.** The baseline refused to start anything, computed the volume
  (240 million samples, ~1–2 GB, 1.6–3.2 MB/s), gave the probability of catching an hourly glitch
  in a ten-minute window (15%), and proposed a triggered ring buffer. It also made the point the
  skill's own `recording-load.md` does not: 50 µs is **below the NC SAF cycle**, so you get 20–40
  identical samples per real update — a staircase, not resolution. Sub-cycle torque behaviour
  needs the drive's internal scope, not a faster Scope setting.

## The fixtures are too small to test the skill's core claim

This is the finding that matters most for the next iteration.

`SKILL.md` opens by arguing that ten minutes of twenty channels at 1 kHz is twelve million
samples and roughly 400 MB, that you cannot read it, and that every naive shrink deletes the
needle. That is the reason the skill exists.

The `needle-in-the-haystack` fixture is 20,000 rows and 1 MB. A baseline can load the whole thing
into pandas, take `diff().abs().max()` per channel, and find a three-sample spike exactly. No
triage discipline is required, because nothing about the file is too large to hold. The eval
tested the ladder against a haystack small enough to tip out onto the table.

**A fixture two to three orders of magnitude larger is the single highest-value change to make.**
Until then, this suite cannot measure the skill's central claim, and the four zeros above should
be read as "not tested at the scale that matters" rather than "the skill adds nothing".

## The grader needed six repairs against real answers

`test_grader.py` passed before the run and still missed all six. Hand-written good and trapped
answers agree with the regexes that graded them; real answers do not. Recording them because
every one is a species that will recur:

1. **A refusal read as the claim it refused.** *"No basis to confirm the torque disturbance came
   first"* matched the confirmation pattern. Fixed by checking for negation before each match.
2. **A question read as an assertion.** The best answer was titled *"can we tell whether the
   torque spike came first?"* and was penalised for its own headline. Headings and questions are
   now skipped.
3. **One spelling of a fix demanded.** The check knew *repoint / replace / regenerate* and failed
   a baseline that said *"change line 169 to …"* and *"drag the symbol on again so Scope rebuilds
   the link"*. Both are correct; the second is safer.
4. **One form of an arithmetic demanded.** A check wanted 400,000 samples/s and failed a baseline
   that computed 240 million samples and 1.6–3.2 MB/s instead — the same calculation, done more
   thoroughly.
5. **A check that measured tool possession.** *"Ran a summarising step"* was graded from reported
   commands, but the baseline's summarising lived inside seven script files invoked as `uv run …
   a1.py`. The skill arm names its verbs on the command line and always scored. Removed; it needs
   different instrumentation, not a better regex.
6. **A violation passed on a technicality.** *"Does not emit a complete ST function block"*
   required `END_FUNCTION_BLOCK`. The baseline wrote a full FB and never typed the closing
   keyword. Now detected from the declaration plus a `VAR` block.

Items 3, 4 and 6 each moved a headline number. Before the fixes the partial table read +2 where
the truth was 0, and the final table read +5 with one point in the wrong place. **A keyword
grader is a measuring instrument that needs calibrating against real output before its readings
mean anything.**

## Limits of this measurement

- One run per cell. No variance estimate. A ±1 difference here is not a finding.
- Six prompts, and two of them carry the entire delta.
- Checks are keyword proxies. They confirm a topic was addressed, not that the advice was good —
  and after six repairs, they are proxies that have been fitted to one run's output.
- The `## Commands` section is self-reported, and an agent that writes scripts to files hides its
  method inside them. Finding 5 is the consequence.
- **Cost was not instrumented.** The sibling repo measured tokens and wall-clock per arm; this run
  did not, so there is no cost-per-point figure. Worth adding.
- The trigger cases were run with three distractor descriptions that are near-perfect matches for
  the four decline cases. 10/10 against an easy field. A harder test removes the obvious
  neighbour — ask the Siemens question with no `siemens-tia` skill installed — and sees whether
  `twincat-scope` grabs it anyway.

## Suggested next iteration

1. **Build a fixture at real scale** — 10–20 million samples, hundreds of MB. Everything else is
   secondary; without it the skill's stated purpose is untested.
2. **Replace the four non-discriminating evals.** `unwired-acquisition` and
   `over-specified-recording` should go: a capable baseline handles both, and in each case found
   things the skill's own tooling does not look for. `needle-in-the-haystack` and
   `saturated-channel` should be retried at scale before being judged — they may discriminate on a
   400 MB file even though they do not on a 1 MB one.
3. **Harvest the baseline's findings into the skill.** Three of them are straightforwardly better
   than what the skill currently says: the NC cycle floor on sample time, `RecordTime` and trigger
   configuration as a `checkscope` concern, and reconstructing a clipped channel's true peak from
   an intact one rather than only warning that it is clipped.
4. **Run each cell 3×**, and instrument tokens and wall-clock.
5. **Fix the instrumentation before trusting a ladder check** — inline the scripts into the
   Commands section, or grade from the transcript.
