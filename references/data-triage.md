# Data triage — twelve million samples, one answer

The core file. Everything else here is vendor detail; this is the method.

## The problem, stated precisely

A ten-minute recording of twenty channels at 1 kHz holds **12,000,000 samples**. As CSV that
is roughly 400 MB. Three things follow, and they are the whole reason this skill exists:

1. **You cannot read it.** Not the file, not a tenth of it, not a "representative sample".
2. **What you are looking for is small.** A torque spike that trips a drive lasts three
   milliseconds — three samples. A following-error excursion that causes a scrap part might
   be twenty. Against 12M samples, that is a needle in six haystacks.
3. **Every naive shrink deletes the needle.** Taking every 100th sample gives you a plottable
   120,000 points and a 3% chance of catching a 3-sample event.

So the rule is absolute: **never move samples into the conversation.** Move *statements about*
samples instead — counts, extremes, timestamps, pictures.

## The ladder

Each rung answers one question and hands the next rung a narrower one. Skipping rungs is how
you end up with a confident wrong answer.

| Rung | Verb | Question | Typical output size |
|---|---|---|---|
| 1 | `manifest` | What is in this file? | ~1 KB |
| 2 | `stats` | Which channel is misbehaving? | ~200 bytes/channel |
| 3 | `events` | When did it happen? | ~100 bytes/event |
| 4 | `plot` | What is the shape around then? | one PNG |
| 5 | `correlate` | Which channel moved first? | ~150 bytes/pair |
| 6 | `window` | What were the actual numbers? | capped, ~500 rows |

Rung 6 exists, and it is capped, and the cap is not negotiable by widening the range. If
500 rows is not enough, the question is still too broad — go back to rung 3 or 4.

### Rung 1 — `manifest`

Cheap and always first. It tells you the sample rate rather than letting you assume it,
which matters because every frequency claim you make downstream is scaled by that number.
Look for: a channel that is entirely constant (dead symbol, wrong index offset), a
`nan_fraction` above zero (parse trouble), and `gaps` above zero (the recording stalled).

### Rung 2 — `stats`

Read these four together, not individually:

- **`pct_at_max` / `pct_at_min`** — time spent pinned at a rail. Above a few percent means
  saturation, and a saturated signal is *lying to you*: its true value went further than the
  recording shows. Diagnose the saturation before anything downstream of it, and see
  *Recovering a clipped channel* below — refusing to give a number is the floor here, not the
  ceiling.
- **`pct_flat`** — a signal that stops changing. Either the machine stopped, or the symbol
  stopped updating. Those are very different problems.
- **`quantisation_step`** — the smallest gap between distinct values. If this is large
  relative to the range, the channel was recorded as an integer type and you are looking at
  a coarse approximation. Do not read fine structure out of a coarse channel.
- **`std` vs `p99 - p01`** — a large gap between them means outliers dominate the standard
  deviation, so thresholds based on σ will be wrong.

#### Recovering a clipped channel

"The channel is clipped, so I cannot tell you the peak" is a correct answer and usually not the
best one. The information is gone *from that channel*. It is often still in the recording,
because machine signals are related to each other by physics:

- **A clipped velocity, with position intact.** Velocity is the derivative of position.
  Differentiate `ActPos` over a smoothing window and you have the peak the velocity channel
  could not show. Same for a clipped acceleration against an intact velocity.
- **A clipped signal with a known shape.** For a sinusoidal move, fit the sine to the samples
  that are *not* pinned — the ones near each reversal — and read the amplitude off the fit.
- **The pinned fraction itself is a measurement.** For a sine of amplitude `A` clipped at level
  `C`, the fraction of time spent at the rail is `1 − (2/π)·arcsin(C/A)`. Observe the fraction,
  solve for `A`. It needs no time axis at all, which makes it a good independent check on the
  other two.

Do all three when you can and say whether they agree — three routes landing on the same number
is what separates a reconstruction from a guess. Then say plainly that the figure is
reconstructed rather than measured, and what would replace it: a re-record with the range or
the scaling fixed.

Worth knowing *why* it clipped before re-recording. A rail at a round number is usually a
scaled integer type or a fixed scope range, not the machine.

### Rung 3 — `events`

Detectors, and what each one actually means on a machine:

| Kind | Physical reading |
|---|---|
| `step` | A discontinuity that stayed — a setpoint jump, a mode switch, an encoder jump, a re-home |
| `ramp` | A commanded move: the signal travelled, but it took many samples to get there |
| `spike` | Something transient — a torque impulse, EMI on an analogue input, a single bad ADC read |
| `transition` | A digital channel changed state |
| `flatline` | The signal stopped updating for a sustained run |
| `clipping` | The signal hit a rail; the true value is unknown beyond it |
| `crossing` | A user-supplied threshold was crossed |

An excursion is **one event however long it lasts**. Reporting each over-threshold sample
separately is what made this verb unusable on real machine data: a single 2.4 s move arrived
as 1199 "steps" and buried every real fault underneath them.

The step/spike distinction is a judgement about *width*, controlled by `--spike-width`. A
value that leaves and returns within that many samples is a spike; one that leaves and stays
is a step. Getting this wrong in either direction is common: too narrow and every spike is
reported twice as a pair of steps, too wide and genuine steps get swallowed. `--ramp-samples`
draws the other boundary: an excursion wider than that is a move rather than a discontinuity.
Both names matter — filtering for `step` is how you find the jumps worth explaining, and a
commanded move is not one of them.

#### Why the threshold has a floor

`--sigma` scales the threshold against the median absolute deviation of the first difference,
not the standard deviation, so a few large outliers do not raise the bar and hide everything
else. On its own that fails badly on exactly the signals this skill exists for. **An axis is
at rest for most of a recording**, so over half its first differences are the encoder's
quantisation floor, MAD collapses to ~1e-9, and 6·MAD·1.4826 becomes a threshold that every
genuine acceleration sample clears. Measured on real exports: 298 events per REAL64 motion
channel, against 10 per digital channel.

So `--min-step` (default 1%) floors the threshold at a fraction of the channel's own travel.
A change worth reporting is exceptional against the quiet stretches **and** a real fraction of
the distance the signal covers. If a known fault is not being found, lower `--sigma` to 3 and
`--min-step` toward 0.001 before concluding the data is clean.

#### Reading a truncated answer

`count` is every event found; `events` is what fits under `--max-events`. The returned set is
the worst event in each tenth of the recording, worst tenth first — so a truncated answer
still spans the recording and still contains the single worst thing in it. `summary` is always
complete regardless: `by_kind`, `by_channel`, `per_channel_max` and a ten-bin `time_histogram`
count *every* event, including the ones not returned. Read the histogram before re-running
with a bigger cap — it tells you which part of the recording to ask about instead.

`severity` is a multiple of each detector's own threshold, so it is comparable within a kind
and only roughly across kinds. `ramp`, `transition` and `crossing` are descriptive rather than
anomalous and are always 1.0.

**Known limitation.** `clipping` fires on an axis parked at the end of its travel, because a
rest position and a rail look identical in the data. Check `stats` → `pct_at_max` and the
`plot` before repeating a clipping claim about a position channel.

### Rung 4 — `plot`, and the one rule that matters

**Use a min/max envelope per pixel bucket. Never decimate.**

A 900-pixel-wide chart of 20,000 samples has 22 samples per pixel column. Decimation picks
one of those 22 and throws away 21 — so a 3-sample spike has roughly a 1-in-7 chance of
appearing at all. Six times out of seven you get a clean-looking chart of a machine that
faulted, which is worse than no chart because it actively argues the wrong case.

The envelope instead draws the **minimum and maximum** within each bucket as a vertical band.
The spike is 22× narrower than the rest of the trace but it is *there*, at full amplitude,
because its extreme survived the reduction. `tcscope.py plot` does this and reports
`"method": "min/max envelope per pixel bucket"` so the choice is visible in the output.

This is why `plot` is a rung of the ladder and not decoration. It is the only step that can
show you something you did not think to ask about.

### Rung 5 — `correlate`

Answers "which one moved first", which is usually the real question. On a machine, causes
precede effects by a measurable lag: the current loop reacts before the velocity loop, which
reacts before position.

**The sign convention:** a **negative** `lag_seconds` means `a` leads `b` — a's features
appear earlier in time. The `leads` field names the channel outright so you never have to
remember this. A lag of the wrong sign is a strong hint that your mental model of the causal
chain is backwards.

Correlation is not causation, and on a machine with a cyclic process almost everything
correlates with almost everything at the cycle period. Treat a high correlation between two
signals that share a driving frequency as uninformative unless the lag says something.

Two more limits worth knowing. Correlation is computed on mean-centred, unit-normalised
signals, so a high-amplitude channel no longer outranks the low-amplitude one that caused
it. And channels from different acquisition groups are refused unless you pass
`--allow-cross-group`: they are sampled on different clocks, so a lag between them is only
meaningful beyond the file's `max_skew_ms`. On an export where
`cross_group_timing_valid` is false, `correlate` refuses outright.

### Rung 6 — `window`

Now, and only now, real numbers — for a range you can justify from rungs 3–5.

## Working rules

- **Name the timestamp.** "Torque spiked" is not a finding. "Torque spiked to 4.2 Nm at
  t=12.001, three samples wide" is.
- **Say what you did not check.** Six channels analysed out of twenty is a fine answer;
  silently implying you looked at all twenty is not.
- **A saturated channel invalidates everything computed from it.** Check `pct_at_max` before
  trusting any mean, RMS or correlation involving that channel.
- **Two plausible causes beat one confident wrong one.** On a shop floor a wrong diagnosis
  costs a day of stripping the wrong subsystem.
- **Cache the Parquet.** `ingest` once per recording, then every subsequent question is
  seconds rather than minutes. The group layout travels in the Parquet schema metadata, so
  per-group time axes survive the round trip.
- **Name the group too, when there is more than one.** Two acquisition groups routinely
  carry the same short channel name. `ActTorque spiked` is ambiguous; `ActTorque (group 1,
  port 851)` is not.
