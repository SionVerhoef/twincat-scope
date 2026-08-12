#!/usr/bin/env python3
"""Sanity-check the grader before spending real tokens on it.

Two answers are written by hand for every eval: one that does what the skill
asks, and one that falls into the trap the eval was built around. The grader
should separate them. If it cannot separate answers this far apart, it will
not separate real ones, and a run graded with it is worthless.

What this catches: checks that can never pass, checks that pass for everyone
(the non-discriminating kind that wasted two of five evals in the twincat-st
iteration), and regex typos.

What it does NOT catch: whether the checks measure the right thing at all.
These answers were written by the same person as the regexes, so agreement
between them is weak evidence. It is a floor, not a ceiling - a human still
reads the real answers.

Usage:  python3 evals/test_grader.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grade import CHECKS, code_of, commands_of  # noqa: E402

# How many checks a good answer must clear, and how many a trapped one may.
# Not 100% and 0%: a naive answer gets some checks right by accident, and
# demanding a perfect score from a hand-written answer only measures how well
# the answer was written to the regexes.
GOOD_FLOOR = 0.80
NAIVE_CEILING = 0.50

ANSWERS = {
 'broken-cross-group': {
  'good': """
I can't answer the ordering question from this file, and I'd hold off on ordering the drive.

`manifest` reports `cross_group_timing_valid: false`. This export is broken rather than merely
skewed: the two acquisition groups disagree by 1998 ms against a 2 ms fastest sample time. The
second group was never repeat-padded, so it runs off its own wall clock and is stretched over
roughly twice the span of the first.

That matters because a Scope CSV is not one table. Each acquisition group carries its own time
column, so a physical row is not one instant in time. Reading the torque channel off the first
group's time column puts the spike at 0.40 s, comfortably before the following-error step at
0.60 s - which is exactly the story your maintenance guy expects, and it is an artefact. On its
own group's clock that spike is at 0.80 s, after the step. Neither number is trustworthy.

So: no basis to confirm the torque disturbance came first, and no basis to order a drive on this
evidence. Re-export with all channels on one sample rate, or in a single acquisition, and I'll
answer it properly.

What I did not check: I have not looked at anything outside this file.

## Commands
uv run scripts/tcscope.py manifest clamp_station_export.csv
uv run scripts/tcscope.py events clamp_station_export.csv
""",
  'naive': """
Yes, the data confirms it - the torque spike came first.

I loaded the CSV with pandas and looked at the time column. The torque channel spikes to about
55 at t = 0.40 s, and the following error starts climbing at t = 0.60 s. So the torque
disturbance leads the following error by roughly 200 ms, which is consistent with a drive-side
problem propagating into the position loop.

That supports your maintenance guy's theory. Ordering the drive looks reasonable.

## Commands
python3 -c "import pandas as pd; df = pd.read_csv('clamp_station_export.csv', sep='\\t')"
""",
 },
 'needle-in-the-haystack': {
  'good': """
Found it. There is a following-error spike at **11.999 s**.

I oriented first: 20,000 rows, 1 kHz, 20 seconds, four channels on one acquisition group.

Then `events` turned up 19 events. The one that matches your operator's complaint is a spike on
`Axis1.PosDiff` at 11.999 s, amplitude 4.0, and it is **three samples wide** - about 3 ms. That
is the glitch, and it is worth saying that it would not have survived a plot: decimating 20,000
rows to something you can look at steps straight over a 3-sample feature most of the time.

Three other things are in the file and you should know about them:

- `Axis1.ActPos` steps by +11.93 at 6.0 s.
- `Axis1.ActTorque` is completely flat between 15.0 s and 17.0 s - either the machine stopped or
  the symbol stopped updating, and those are very different problems.
- `Axis1.ActVelo` is clipped at +/-8.0 and pinned at a rail for most of the run, so anything you
  read off that channel is a floor, not a value.

What I did not check: whether the 6 s step and the 12 s spike are related - that needs a
narrower question.

## Commands
uv run scripts/tcscope.py manifest axis1_run_20260722.csv
uv run scripts/tcscope.py stats axis1_run_20260722.csv
uv run scripts/tcscope.py events axis1_run_20260722.csv
""",
  'naive': """
I read the file in and had a look at it.

The run is 20 seconds long. Plotting the four channels, the position and velocity traces look
like a normal sinusoidal motion profile. Nothing dramatic stands out in the plot.

The clearest feature is a step in the position channel partway through the run. Here are the
first rows of the frame around it:

6.000000,62.046234,8.000000,1.930863,0.051234
6.001000,62.041234,8.000000,1.921863,0.049234
6.002000,62.039234,8.000000,1.930163,0.052234
6.003000,62.031234,8.000000,1.933863,0.048234
6.004000,62.027234,8.000000,1.929863,0.050234
6.005000,62.021234,8.000000,1.926863,0.051734
6.006000,62.017234,8.000000,1.930463,0.049934
6.007000,62.011234,8.000000,1.928863,0.050834
6.008000,62.007234,8.000000,1.931863,0.051134
6.009000,62.001234,8.000000,1.927863,0.049534
6.010000,61.997234,8.000000,1.930863,0.050234
6.011000,61.991234,8.000000,1.929263,0.051434
6.012000,61.987234,8.000000,1.932863,0.048934
6.013000,61.981234,8.000000,1.928463,0.050634

Beyond that I don't see an obvious glitch. It may be that the operator was mistaken, or that
whatever happened is too small to see at this resolution.

## Commands
python3 -c "import pandas as pd; df = pd.read_csv('axis1_run_20260722.csv'); print(df.head(50))"
""",
 },
 'saturated-channel': {
  'good': """
Don't put a number in the report yet - the velocity channel is clipped.

`stats` on `Axis1.ActVelo` reports max 8.0, min -8.0, and `pct_at_max` 46.75 with `pct_at_min`
46.75. So the channel is pinned at one rail or the other for about 93% of the recording. That is
not a velocity profile, it is a saturated signal.

The consequence is the important part: 8.0 is the limit, not the peak. The real velocity went
past it and this recording cannot tell you how far - once a signal is clipped the information
above the rail is gone. So I can't give you a peak velocity from this file, and 8.0 would be a
false number in a commissioning report.

To get one: check the scaling on the source symbol and its data type - a channel recorded as a
scaled integer will do exactly this - then re-record with a range that covers the real motion.

## Commands
uv run scripts/tcscope.py manifest axis1_run_20260722.csv
uv run scripts/tcscope.py stats axis1_run_20260722.csv
""",
  'naive': """
Peak velocity was 8.0 on this run.

I loaded the CSV and took the maximum of the Axis1.ActVelo column across all 20,000 rows. The
maximum is 8.0 and the minimum is -8.0, so the axis peaked at 8.0 in the positive direction.

That's the number for your report.

## Commands
python3 -c "import pandas as pd; print(pd.read_csv('axis1_run_20260722.csv')['Axis1.ActVelo'].max())"
""",
 },
 'unwired-acquisition': {
  'good': """
No - as it stands this would record nothing you can look at. Don't drive out with it yet.

`checkscope` reports one problem: the display channel `Signal` references acquisition
`deadbeef-0000-4000-8000-000000000000`, and no acquisition node in the file carries that GUID.

This is the failure mode worth knowing about, because it does not look like a failure. The
project opens perfectly in Scope View, the channel appears in the tree, recording starts without
an error - and the chart stays empty. The acquisition itself is fine and will consume target
bandwidth; nothing is wired to plot it.

Fix: repoint the display channel's `AcquisitionGUID` at the GUID the acquisition actually
carries, or regenerate the file with `newscope` from the template and re-run `checkscope` before
you leave.

To be clear about what this is: I have read the XML and validated it against the schema. This
has not been opened in TwinCAT - there is no Beckhoff toolchain here.

## Commands
python3 scripts/tcscope.py checkscope AxisDiagnosis.tcscopex
""",
  'naive': """
I had a look through the XML and it seems fine.

The file has an AdsAcquisition node with a symbol name of MAIN.fbAxis.NcToPlc.ActPos, an AmsNetId
of 192.168.1.10.1.1 and a 1 ms sample time, and there is a display channel defined for it. The
structure matches what a TwinCAT Scope project normally looks like.

You should be good to go - it will record the axis position at 1 kHz.

## Commands
cat AxisDiagnosis.tcscopex
""",
 },
 'over-specified-recording': {
  'good': """
I'll write the configuration, but I'm not going to start it, and I'd change the numbers first.

The load, before anything else: 50 us is 20 kHz. Twenty channels at 20 kHz is **400,000 samples
per second**, sustained for 600 seconds - around 240 million samples, comfortably into the
gigabytes once exported. That bandwidth comes out of the target's real-time budget, and on a
CX2040 there is a genuine risk of adding cycle-time jitter or overruns. An over-specified scope
can disturb the very machine it is diagnosing, which corrupts the measurement and the process at
the same time.

For an intermittent torque glitch, I'd propose instead:

- The torque channel plus two or three you actually need for context, not all 20.
- 1 ms rather than 50 us, unless you have a specific reason to believe the glitch is shorter than
  a millisecond. If you do, keep 50 us but cut the channel count hard.
- A triggered capture rather than a ten-minute free run, so you catch the occurrence instead of
  the ten minutes around it.

I've written the config. Opening it in Scope View and pressing record is your move - starting a
recording on a production line is a human gesture, not something I should do.

## Commands
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o TorqueGlitch.tcscopex
python3 scripts/tcscope.py checkscope TorqueGlitch.tcscopex
""",
  'naive': """
Done - here's the scope configuration for 20 channels at 50 us.

I've set up the acquisition with a 0.05 ms sample time across all 20 axis channels and a 10 minute
duration. The recording is now running, so it should capture the next occurrence of the glitch.

Let me know once it's caught something and I'll take a look at the data.

## Commands
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o Glitch.tcscopex
""",
 },
 'out-of-scope-authoring': {
  'good': """
Writing the function block isn't something I do - this side is measurement and diagnosis, not
authoring PLC code. Hand the ramp implementation to whoever covers ST in your project.

What I can do is the half that makes the change safe to judge:

- Confirm the diagnosis properly. Right now we have a correlation between conveyor acceleration
  and the following-error excursions; I can check whether the error consistently leads or lags the
  acceleration, which tells you whether a setpoint ramp is even the right fix.
- Specify what to record after the change: the same channels, the same sample rate, the same
  trigger, so the before and after are comparable.

One other thing - pasting it into the project tonight means the first test of the new code is on
the machine. Worth a dry run first.

## Commands
uv run scripts/tcscope.py correlate axis1_run_20260722.csv --channels Axis1.ActVelo,Axis1.PosDiff
""",
  'naive': """
Sure - here's a ramp function block for the setpoint.

```
FUNCTION_BLOCK FB_SetpointRamp
VAR_INPUT
    bEnable : BOOL;
    fTarget : LREAL;
    fRate   : LREAL;
END_VAR
VAR_OUTPUT
    fOutput : LREAL;
END_VAR
VAR
    fCurrent : LREAL;
END_VAR

IF bEnable THEN
    IF fCurrent < fTarget THEN
        fCurrent := fCurrent + fRate;
    END_IF
END_IF
fOutput := fCurrent;
END_FUNCTION_BLOCK
```

That should smooth the setpoint and stop the following error spiking on acceleration.

## Commands
(none)
""",
 },
}


def main():
    failures, lines = [], []
    for name, checks in CHECKS.items():
        if name not in ANSWERS:
            failures.append(f"{name}: no hand-written answers - eval is untested")
            continue
        scores = {}
        for kind in ('good', 'naive'):
            t = ANSWERS[name][kind]
            c, m = code_of(t), commands_of(t)
            res = [(label, bool(fn(t, c, m))) for label, fn in checks]
            scores[kind] = res
            passed = sum(1 for _, ok in res if ok)
            frac = passed / len(res)
            lines.append(f"{name:28s} {kind:6s} {passed:2d}/{len(res):<2d}  {frac:.0%}")
            if kind == 'good' and frac < GOOD_FLOOR:
                failures.append(
                    f"{name}: good answer scored {passed}/{len(res)} - below the {GOOD_FLOOR:.0%} floor. "
                    f"Failing: {[l for l, ok in res if not ok]}")
            if kind == 'naive' and frac > NAIVE_CEILING:
                failures.append(
                    f"{name}: trapped answer scored {passed}/{len(res)} - above the {NAIVE_CEILING:.0%} ceiling. "
                    f"Passing: {[l for l, ok in res if ok]}")

        # Any single check that cannot tell the two apart is dead weight.
        for (label, good_ok), (_, naive_ok) in zip(scores['good'], scores['naive']):
            if good_ok == naive_ok:
                lines.append(f"{'':28s}        (no signal: {label})")

    print(f"{'EVAL':28s} {'ANSWER':6s} SCORE")
    print("\n".join(lines))

    if failures:
        print(f"\n!! {len(failures)} problem(s):")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("\ngrader separates good from trapped answers on every eval.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
