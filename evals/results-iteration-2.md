# Eval results — iteration 2: the two evals that tied, re-run at scale

Iteration 1 scored **6/6 in both arms** on `needle-in-the-haystack` and `saturated-channel`, and
recorded those zeros as "not tested at the scale that matters" rather than "the skill adds
nothing". This is that test.

Their fixture was 20,000 rows and 1 MB — a haystack you can tip out onto the table. A baseline
that loads the whole file and takes `diff().abs().max()` finds a three-sample spike every time,
and did. The scaled twins run the same two traps against the file SKILL.md's opening argument is
actually about.

Run 2026-09-16. **One run per cell.** The README's own floor for calling a difference real is
three, so nothing below is offered as a measured delta.

## Setup

| | |
|---|---|
| Fixture | `axis_run_20260904.csv` — 600,000 rows × 20 channels, **12,000,000 samples, 127 MB**, 10 minutes at 1 kHz |
| Written by | `evals/make_eval_fixture.py --scale`, streamed a row at a time, gitignored |
| Planted (Axis1 only) | PosDiff spike +4.0 at **413.777 s**, 3 samples · ActPos step +12.0 at **128.431 s** · ActTorque frozen **291.004–293.517 s** · ActVelo clipped ±8.0 while the motion reaches 78.5 |
| Haystack | Axes 2–4 move normally and none of them saturates |
| Arms | Same model both arms; both told `uv run --with pandas,numpy` was available |
| Staging | Fixture outside the repo; the baseline arm was told not to read anything under it |

Defect placement was checked against the written file before the run: three samples over 2.0 at
413.776/.777/.778, ActPos 31.254 → 43.404 across row 128,431, torque identically 1.500 through the
window, and 93.50% of ActVelo samples sitting exactly on a rail.

## Score

| Eval | With skill | Baseline | Δ |
|---|---|---|---|
| `needle-at-scale` | 6/6 | 5/6 | +1 |
| `saturated-at-scale` | 6/6 | 6/6 | **0** |
| **Total** | **12/12** | **11/12** | +1 |

**Two checks were widened after reading the answers**, which is worth stating plainly because
loosening a check once you have seen the answers is how a harness talks itself into the result it
wanted. Both were vocabulary gaps rather than judgement:

- *reports the spike is only a few samples wide* did not match "for exactly **4** samples", which
  states a width without ever saying "wide".
- *proposes a fix* did not match "**re-export** at the correct **scale/range**", which is a fix
  proposal by any reading; the pattern only knew "re-record" and "rescale".

Before the widening the table read 5/6 vs 5/6 and 6/6 vs 5/6 — the same total, with the +1 landing
on the other eval. The hand-written naive answers still score **0/6** on both evals afterwards, so
the checks did not become free.

## What the answers actually show

### The saturated channel does not discriminate at any size

The baseline identified the clip unprompted, quantified it (280,497 samples at exactly +8.000000,
280,516 at −8.000000, "93.5% of all 600,000 samples"), refused to put 8.0 in the report,
cross-checked against the unclipped position channel, and proposed a fix. It also reasoned from
the neighbours — Axis2–4 peak near 27.6 and each peak occurs once, "that's what a normal,
unclipped velocity peak looks like" — which is the comparison the fixture was built to allow.

Scaling this trap 30× changed nothing, because the signature it rests on is statistical: a
channel pinned at a bit-exact value for 93% of a run is as obvious in 12 million samples as in
20,000. **This eval should be retired or replaced**, not re-run at n=3. It has now measured
nothing twice.

### The needle: one real difference, and a flaw in the question

Both arms found the 3-sample spike at 413.776–413.778 s. Both also found the position step at
128.431 s, and **both concluded the step was the more likely cause of a bad part** — it never
corrects, so the axis runs the remaining eight minutes mis-registered by 12 units, whereas the
spike self-corrects in 3 ms and moves nothing else. That is a defensible reading, and it is not
the one the eval asserts.

The one behavioural difference: **the baseline missed the frozen torque channel entirely.** It
mentioned torque fifteen times, always as evidence that nothing disturbed the axis at the step,
and never noticed that `Axis1.ActTorque` is identically 1.500 for two and a half seconds around
291 s. The skill arm reported it as its own finding — a flatline detector fires on it whether or
not you thought to look, which is the difference between a ladder and an idea.

The skill arm was not flawless: it reported the spike as "exactly 4 samples (413.776–413.778 s)",
which is three samples at 1 kHz. Right event, right window, off-by-one on the count.

**The question is flawed at this scale.** Asking "what happened, and when" against a file with two
planted, unrelated, independently-defensible candidate events cannot be graded on an assertion
that names one of them as "the glitch". Iteration 1 got away with it because at 20,000 rows both
arms simply listed everything. The fix for iteration 3 is to plant one candidate event in the
scaled fixture, or to ask a question whose answer is the full list.

## Cost, which is the measurement that was supposed to decide this

The bead that ordered this test predicted the scores would tie, and said that if they did, the
skill's value would be token economy rather than correctness — a *cost* measurement. It also said
to instrument cost **before** running, or the result would be uninterpretable.

That instrumentation is only half built. **Per-arm token counts were not captured** — this harness
drives agents that do not report their own usage, so the number the argument actually rests on is
still missing.

What the run did leave behind:

| Cell | Shell commands | Scratch scripts written | Answer prose |
|---|---|---|---|
| `needle-at-scale` / with skill | 18 | 0 | 6,153 chars |
| `needle-at-scale` / baseline | 15 | 6 | 3,793 chars |
| `saturated-at-scale` / with skill | 26 | 0 | 2,708 chars |
| `saturated-at-scale` / baseline | 8 | 0 | 2,670 chars |

**On every proxy available, the skill arm was not cheaper.** It ran more commands in both evals
and finished later in both. Some of that is real and expected — it reads `SKILL.md` and its
references before touching the file, and in the needle case it converted the export to Parquet
first. Wall clock is not reported here as a number because all four cells ran concurrently on one
machine and competed for it; the ordering survives that confound, the durations do not.

So the honest position after iteration 2 is:

- The scale hypothesis is **disproved for the saturated channel** and **not supported for the
  needle**: the baseline's method scales, exactly as the bead warned it might.
- The one thing the skill arm did that the baseline did not was **surface a defect nobody asked
  about**. That is a coverage difference, not a correctness difference, and it is the argument
  worth testing properly next.
- The cost claim remains **unmeasured**, and cannot be settled by this harness until it records
  tokens per arm.

## What to change before iteration 3

1. **Instrument tokens per arm.** Until then, do not re-run either of these evals: the outcome is
   already known to be a tie or near-tie on score, and the interesting axis is not being recorded.
2. **Retire or replace `saturated-channel` and `saturated-at-scale`.** Two runs, two full-mark
   ties, four cells of budget spent on a trap a capable baseline walks around unaided.
3. **Re-cut the needle fixture with one planted event**, or change the question to "list everything
   anomalous in this file and rank it". As written, the eval punishes the ranking both arms
   reached independently.
4. **Keep the 20,000-row pair** alongside the scaled pair. The comparison between the two sizes is
   the only reason the iteration-1 zeros are interpretable at all.
