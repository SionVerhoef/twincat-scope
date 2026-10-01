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
 'needle-at-scale': {
  'good': """
Found it. There is a following-error spike on Axis 1 at **413.777 s** - about 6 minutes 54 into
the run.

I oriented first rather than opening the file: 600,000 rows at 1 kHz, 20 channels across four
axes, 10 minutes, one acquisition group, no gaps. That is 12 million samples and ~127 MB, so
nothing here involved reading rows into this conversation.

`events` ranks it first: a spike on `Axis1.PosDiff`, amplitude 4.0, **three samples wide** - 3 ms.
That is your glitch, and it is worth saying why nobody saw it: three samples in twelve million.
Any decimation that makes this file plottable steps over it, and so does head, tail and eyeballing.

Two other things in the same file that you should know about:

- `Axis1.ActPos` steps by +12.15 at 128.431 s. That is a real discontinuity, not drift.
- `Axis1.ActTorque` is flat at 1.500 from 291.004 s to 293.517 s - either the machine stopped or
  the symbol stopped updating, and those are very different problems.

Also, `Axis1.ActVelo` is clipped at +/-8.0 for most of the run, so any velocity you read off that
channel is a rail rather than a value. The other three axes are not clipped.

What I did not check: whether the step and the spike share a cause. That needs a narrower question.

## Commands
uv run scripts/tcscope.py manifest axis_run_20260904.csv
uv run scripts/tcscope.py stats axis_run_20260904.csv
uv run scripts/tcscope.py events axis_run_20260904.csv
uv run scripts/tcscope.py window axis_run_20260904.csv --start 413.77 --end 413.79 --channels Axis1.PosDiff
""",
  'naive': """
I loaded the file and had a look at it.

It is a big file, so I sampled every 500th row to get something plottable. The four axes all show
normal sinusoidal motion. Nothing dramatic stands out.

The clearest feature is a step in the Axis 1 position channel partway through. Here are rows from
around it:

128431.000000,43.404192,43.401000,8.000000,1.930863,0.051234
128432.000000,43.398192,43.395000,8.000000,1.921863,0.049234
128433.000000,43.392192,43.389000,8.000000,1.930163,0.052234
128434.000000,43.386192,43.383000,8.000000,1.933863,0.048234
128435.000000,43.380192,43.377000,8.000000,1.929863,0.050234
128436.000000,43.374192,43.371000,8.000000,1.926863,0.051734
128437.000000,43.368192,43.365000,8.000000,1.930463,0.049934
128438.000000,43.362192,43.359000,8.000000,1.928863,0.050834
128439.000000,43.356192,43.353000,8.000000,1.931863,0.051134
128440.000000,43.350192,43.347000,8.000000,1.927863,0.049534
128441.000000,43.344192,43.341000,8.000000,1.930863,0.050234
128442.000000,43.338192,43.335000,8.000000,1.929263,0.051434

Beyond that I do not see an obvious glitch. The operator may have been mistaken, or whatever
happened is too small to see at this sampling.

## Commands
uv run --with pandas python -c "import pandas as pd; df = pd.read_csv('axis_run_20260904.csv', skiprows=5); print(df.iloc[::500].describe())"
""",
 },
 'saturated-at-scale': {
  'good': """
Short answer: **the number in that file is not the peak, and you should not put 8.0 in the report.**

`Axis1.ActVelo` is hard-clipped at +/-8.0. `stats` reports 93.50% of the run pinned at one rail or
the other (pct_at_max 46.75, pct_at_min 46.75) - a real velocity trace does not sit at exactly its
maximum for that long. The recorded maximum is the clip, not the motion.

The peak is recoverable, because the position channel is not clipped. `Axis1.ActPos` is a clean
0.25 Hz sinusoid of amplitude 50.0, so the peak velocity is 50.0 * 2*pi * 0.25 = **78.5 units/s**.
The other three axes are not clipped and peak around 27, which is what makes the Axis 1 rail a
finding rather than the house style.

For the commissioning report: 8.0 is not safe to put in the report as-is - it would be a
documented false number. Use 78.5 with a note that it was reconstructed from position, or
re-record before signing anything off. The fix on the recording side is the channel's scaling
or its source data type - a value that stops dead at exactly 8.0 is usually a scale factor or a
type that cannot hold the real range.

## Commands
uv run scripts/tcscope.py manifest axis_run_20260904.csv
uv run scripts/tcscope.py stats axis_run_20260904.csv --channels Axis1.ActVelo,Axis1.ActPos
""",
  'naive': """
The peak velocity on Axis 1 during this run was **8.0**.

I read the file with pandas and took the maximum of the `Axis1.ActVelo` column. The maximum is
8.000000 and the minimum is -8.000000, so the axis peaked at 8.0 in both directions. That is
consistent across the whole ten minutes.

You can put 8.0 in the commissioning report as the peak velocity for this axis.

## Commands
uv run --with pandas python -c "import pandas as pd; df = pd.read_csv('axis_run_20260904.csv', skiprows=5); print(df['Axis1.ActVelo'].max(), df['Axis1.ActVelo'].min())"
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
of 1.2.3.4.1.1 and a 1 ms sample time, and there is a display channel defined for it. The
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
 'multi-rate-ordering': {
  'good': """
I can't confirm it, and I wouldn't clear the drive on this file.

The export itself is fine - `manifest` says cross-group timing is valid - but the two channels
you are asking about are in different acquisition groups. `PosDiff` is sampled every 1 ms;
`ActTorque` every **10 ms**.

Per group, on each group's own clock: the following error starts rising at 0.405 s. The torque
reads normal at 0.400 s and high at 0.410 s. So the torque rose somewhere between 0.400 and
0.410 s, and 0.405 is inside that window. The 5 ms gap between the two is less than one torque
sample, so the order is not in this data - either could have come first.

Re-record with the torque on the same 1 ms rate as the following error (one acquisition group)
and the question answers itself.

What I did not check: anything outside this file.

## Commands
uv run scripts/tcscope.py manifest press_line_export.csv
uv run scripts/tcscope.py events press_line_export.csv
""",
  'naive': """
Yes, your controls guy is right. The following error started climbing at 0.405 s and the torque
spike only shows up at 0.410 s, so the following error came first and the torque reacted to it.
That points at a mechanical cause rather than the drive.

## Commands
python3 -c "import pandas as pd; df = pd.read_csv('press_line_export.csv', skiprows=6); print(df.iloc[395:425])"
""",
 },
 'armed-but-not-recording': {
  'good': """
I don't think the jam is in this file, and I can tell that without reading a single sample.

A `.svdx` carries the whole scope project as XML after the samples, and `checkscope` reads it.
Your trigger group is there and enabled, but its `TriggerAction` is `NONE` - that is how Scope
View stores **Set Mark**. Set Mark marks the moment the jam sensor rises; it does not start or stop
the recording. `RecordTime` is 60 s and the recording does not restart, so this file is one fixed
60 s window from when you pressed Record yesterday afternoon. A jam at 03:12 is hours outside it.

I also can't read the samples here: converting them needs `TC3ScopeExportTool.exe`, which comes
with TwinCAT. So I won't describe what the axis did before the jam - nothing here shows it.

For tonight, set the trigger's action to **Stop Record** with a pre-trigger of, say, 30 s, so the
recording keeps running until the jam and keeps the seconds before it.

What I did not check: the sample data itself.

## Commands
python3 scripts/tcscope.py checkscope filler_overnight.svdx
""",
  'naive': """
Good news - the trigger on the jam sensor is configured, so the recording should include the jam.
The jam is in the file around 03:12; you just need to export it.

A .svdx is a binary Beckhoff format, so I can't open it on a laptop without TwinCAT. Export it to
CSV in Scope View, jump to 03:12, and look at the position and torque in the seconds before.
Just before the jam the axis was most likely decelerating into the stop.

## Commands
file filler_overnight.svdx
""",
 },
 'hand-written-config': {
  'good': """
Not ready as written - the three axis channels would not record. Two problems, both on the
`Axes.Axis1.*` channels; `checkscope` reports six problems, two per channel:

1. **Port.** They are on `TargetPort` 851. That is the PLC runtime's port, and right for
   `MAIN.fbStation.nState`, but NC axis symbols are served by the NC runtime on **501**. On 851
   Scope reports them as unknown symbols.
2. **Type.** They are typed `LREAL`, the IEC name. Scope uses its own vocabulary - the 8-byte
   float is `REAL64` - and it reads `LREAL` as VOID and refuses the channel.

The PLC state channel is fine as it is.

Fix: set `<TargetPort>501</TargetPort>` and `<DataType>REAL64</DataType>` on the three axis
acquisitions, or regenerate the file with `newscope`, which derives both from the symbol names.

## Commands
python3 scripts/tcscope.py checkscope Commissioning_Axis1.tcscopex
""",
  'naive': """
It looks right to me. All four channels point at the PLC on port 851 with symbol-based access,
and the types match the declarations - LREAL for position, following error and torque, INT for
the state variable. The sample time and record time are sensible for a commissioning visit.

## Commands
grep -n "SymbolName\\|TargetPort\\|DataType" Commissioning_Axis1.tcscopex
""",
 },
 'overnight-ring-buffer': {
  'good': """
The jam isn't in this file, and I can tell that from the project it carries, without reading a
single sample.

A `.svdx` ends with the whole scope project as XML, and `checkscope` reads it. Its `StopMode` is
`ClientStop`: that is Scope View's **Ringbuffer** setting. A ring buffer records until someone
stops it and keeps only the last `RecordTime` - here 600 s - before the stop, overwriting
everything older. Your trigger's action is `NONE`, which is **Set Mark**: it marks the jam but
does not stop the recording. So the recording ran on until you stopped it at about 07:40, and the
file holds roughly the ten minutes before that stop, 07:30-07:40. The jam at 03:12 was
overwritten hours ago.

I also can't read the samples here - that needs TC3ScopeExportTool.exe, which comes with TwinCAT -
so I won't guess what the axis did before the jam.

For tonight: keep the ring buffer, but set the trigger's action to **Stop Record** on the jam
sensor with a pre-trigger of 30-60 s. The jam then stops the recording itself, and the file holds
the lead-up.

## Commands
python3 scripts/tcscope.py checkscope filler_overnight.svdx
""",
  'naive': """
Good news - you stopped the recording this morning, so it ran all night and the jam at 03:12 is
in the file. The trigger on the jam sensor should have marked it too.

A .svdx is Beckhoff's binary format, so I can't open it without TwinCAT. Open it in Scope View,
jump to 03:12 and look at position and torque in the seconds before the jam. Just before a jam
the axis is usually decelerating into the stop.

## Commands
file filler_overnight.svdx
""",
 },
 'second-site-config': {
  'good': """
Not ready - two things would stop it working, and neither looks wrong at a glance.
`checkscope` reports both:

1. **Sample time.** `BaseSampleTime` is counted in 100 ns ticks, not milliseconds. The `1` on
   every channel asks for 100 ns - `checkscope` puts the four channels at ~40 000 000 samples/s.
   1 ms is `10000`. Set `<BaseSampleTime>10000</BaseSampleTime>` on all four.
2. **Port on the PLC channels.** `bClamped` and `nState` are on `TargetPort` 801. That is where
   the PLC answered in TwinCAT 2; a TwinCAT 3 PLC runtime starts at **851**. On 801 they find
   nothing. Change both to 851.

The axis channels on 501 are right. Or regenerate the file with `newscope`, which writes both
correctly.

## Commands
python3 scripts/tcscope.py checkscope Line2_Clamp_Scope.tcscopex
""",
  'naive': """
It looks right. All four channels sample every 1 ms (`BaseSampleTime` 1), the axis signals are
on the NC port and the clamp flag and state are on the PLC port 801. The record time of 60 s is
fine for a first look. Send it.

## Commands
grep -n "BaseSampleTime\\|TargetPort" Line2_Clamp_Scope.tcscopex
""",
 },
 'tc2-port-config': {
  'good': """
Not ready - one thing would stop half of it recording, and it doesn't look wrong at a glance.

The two PLC channels, `bClamped` and `nState`, are on `TargetPort` 801. That is where the PLC
answered in TwinCAT 2; a TwinCAT 3 PLC runtime starts at **851** (852, 853... for further
runtimes). On 801 they find nothing. `checkscope` warns on both. Change them to 851.

The rest is right: the axis channels on 501 are the NC runtime's port, and `BaseSampleTime`
10000 is 1 ms. Or regenerate the file with `newscope`, which writes the ports from the symbols.

## Commands
python3 scripts/tcscope.py checkscope Line2_Clamp_Scope.tcscopex
""",
  'naive': """
It looks right. The axis signals are on the NC port 501, the clamp flag and state are on the PLC
port 801, and every channel samples at 1 ms (`BaseSampleTime` 10000). Send it.

## Commands
grep -n "BaseSampleTime\\|TargetPort" Line2_Clamp_Scope.tcscopex
""",
 },
 'export-batch-script': {
  'good': """
Don't schedule it yet - it will not do what you mean, and it will log "export OK" every morning
while failing. Three problems, none of which you can see in the file:

1. **No `silent`.** Without it `TC3ScopeExportTool.exe` opens its window and waits. Under Task
   Scheduler nobody closes it, so the task never finishes.
2. **`channellist=` needs `;`.** With `,` the tool ignores the list and exports every channel.
   Write `channellist=ActPos;ActTorque;bJamSensor`.
3. **`start=`/`end=` are absolute FILETIME ticks** (UTC, 100 ns since 1601) - the numbers the CSV
   header prints as `Starttime of export`. Milliseconds from the start are ignored and the full
   range is exported. Compute the ticks for 03:00 and 03:10 each night.

Points 2 and 3 exit 0, so `errorlevel` never sees them. Check the output instead: its columns and
its header's start and end times.

## Commands
cat nightly_export.cmd
""",
  'naive': """
Looks good to me. The parameters are right - svd=, target=, a channel list and a start/end range -
and you check errorlevel and log the result, which is exactly what you want for an unattended job.
Maybe quote the paths in case they ever get spaces.

## Commands
cat nightly_export.cmd
""",
 },
 'scaled-export': {
  'good': """
I can't answer that from this file, and I wouldn't let it decide the drive either way.

`ActTorque` peaks at about 79 at 3.5 s. But `manifest` shows that channel carries a scaling in
Scope - ScaleFactor 2, Offset 10 - and Scope View only applies it to exported values when
**Scale values before export** is ticked. The header is written the same either way, so the file
does not record which:

- if that option was on, 79 is the scaled value and the peak was about 79 %;
- if it was off (the dialog's default), the values are raw, and the scaled peak is
  2 x 79 + 10 = about 168 %.

One is well under 150 %, the other over. Tell me which setting was used, or send the .svdx and
I'll re-export it with the export tool, which writes raw values, and apply the scaling once.

## Commands
uv run scripts/tcscope.py manifest press_axis3_export.csv
""",
  'naive': """
Yes - it went over. The torque column peaks at 79.0 at 3.507 s, and the header gives the channel
a ScaleFactor of 2 and an Offset of 10, so the real torque was 2 x 79 + 10 = 168 %. That is well
above the 150 % threshold, so the overload warning was genuine and the bigger drive is justified.

## Commands
head -30 press_axis3_export.csv
""",
 },
}

# Real answers the grader once scored wrong. Each is (eval, check label, answer):
# the named check must PASS on it. Iteration 5, read against the judge.
EXTRA_PASSES = [
 ('broken-cross-group', "does not confirm 'torque spike came first'", """
Reading row for row on group 0's 2 ms clock, the torque spike (row 200 = 0.4 s) comes *before* the
following error (row 300 = 0.6 s). On group 1's own clock it is at 0.8 s, after. The export is
broken; neither order holds.
"""),
 ('broken-cross-group', "does not assert the 0.4 s artefact as the torque time", """
Reading row for row on group 0's 2 ms clock, the torque spike (row 200 = 0.4 s) comes *before* the
following error (row 300 = 0.6 s). On group 1's own clock it is at 0.8 s, after.
"""),
 ('tc2-port-config', "says it is not ready as written", """
Not yet. The file is well-formed and wired correctly, but one setting is wrong. `nState` is
`INT16`/2 bytes. That is correct if `nState` is an `INT`; the port is not.
"""),
 ('tc2-port-config', "port 801 is wrong for TwinCAT 3, which starts at 851", """
**The PLC channels are on port 801 instead of 851.** `bClamped` and `nState` both use `TargetPort`
801, where no TwinCAT 3 PLC runtime answers.
"""),
 # Iteration 6: three skill answers the judge scored 2 and this check failed.
 # None says "I won't write it"; each says the skill does not cover it.
 ('out-of-scope-authoring', "declines to author the FB, and gives scope as the reason", """
**Also:** the skill I was given for this covers measurement and diagnosis only; writing or reviewing
Structured Text is explicitly outside it.
"""),
 ('out-of-scope-authoring', "declines to author the FB, and gives scope as the reason", """
There is also a scope limit: the skill I was told to follow covers measurement and diagnosis and
explicitly excludes authoring Structured Text.
"""),
 ('out-of-scope-authoring', "declines to author the FB, and gives scope as the reason", """
- **The scope skill I was pointed at does not cover writing ST.** It is for measurement and
  diagnosis only, and says to hand the code fix elsewhere.
"""),
 ('out-of-scope-authoring', "points the authoring work somewhere else", """
Once the data has named the cause, the ST (if ST is the fix at all) should be written with whatever
covers PLC authoring in your project.
"""),
 ('scaled-export', "opens with the answer: this file cannot settle it", """
# Did the torque go over 150 %?

**This export cannot settle it: the peak is either 79.0 % or 167.9 %, depending on one Scope View
export setting.**
"""),
 ('scaled-export', "opens with the answer: this file cannot settle it", """
**I can't tell you yes or no from this file alone: the answer depends on one export setting the CSV
does not record.**
"""),
 ('needle-in-the-haystack', "does not list the axis's normal standstill creep as a defect", """
### 1. Position step at 6.0 s

`ActPos` jumps by 12 units. Apart from that, `ActPos` drifts a few hundredths away from `SetPos`
over the run; that is what a real axis does and I have not listed it.
"""),
]

# Traps a single 'naive' answer cannot carry. Each is (eval, check label, answer):
# the named check must FAIL on the answer.
EXTRA_TRAPS = [
 ('out-of-scope-authoring', "declines to author the FB, and gives scope as the reason", """
I'd hold off on writing a ramp - I don't think a setpoint ramp is the right fix here. The following
error tracks acceleration, which points at the feed-forward, not the setpoint.
"""),
 ('hand-written-config', "does not flag the PLC state channel as wrong", """
Not ready: the ports are wrong. Every channel should be on 501 - move all four acquisitions
there - and LREAL should be REAL64.
"""),
 ('second-site-config', "does not flag the NC channels on 501 as wrong", """
Not ready: set every channel to 851 and BaseSampleTime to 10000 - 1 is 100 ns, not 1 ms.
"""),
 ('overnight-ring-buffer', "identifies a ring buffer that keeps the last RecordTime before the stop", """
RecordTime is 600 s, so the file holds the first ten minutes after you pressed Record yesterday
afternoon. The jam at 03:12 is long after that.
"""),
 # Iteration 5's baseline: kept the axis on 851 and mentioned 501 only in passing.
 ('hand-written-config', "NC axis channels belong on port 501, not 851", """
Not ready. On port 851 an axis is normally an AXIS_REF, so the paths would be
`GVL.Axis1.NcToPlc.ActPos` - check them. For following error at its true resolution, record the
NC axis directly (port 501, from the NC task). And LREAL should probably be REAL64.
"""),
 ('tc2-port-config', "does not flag the NC channels on 501 as wrong", """
Not ready: 801 is the TC2 port, so set the PLC channels to 851. Also check the axis channels - NC
axis data normally sits under the NC server (port 500).
"""),
 ('tc2-port-config', "port 801 is wrong for TwinCAT 3, which starts at 851", """
Not ready: the sample time is wrong. The PLC channels are on port 801, which is the PLC port, and
the axis channels on 501; both are correct.
"""),
 ('scaled-export', "neither backs nor rules out the bigger drive on this file", """
No. The torque column peaks at 79 %, well under 150 %, so the drive never got near its overload
threshold. The header's ScaleFactor is only for display.
"""),
 ('export-batch-script', "says channellist= needs ';' and that ',' exports every channel", """
Add `silent`, or the tool opens a window and waits. The channel list looks right.
"""),
 ('out-of-scope-authoring', "does not offer to write the block anyway", """
Writing the function block is outside the scope of what I do here - I measure and diagnose. That
said, if you still want it I can put together a quick ramp FB for you to adapt.
"""),
 # Iteration 6: the skill arm's answer, three times. It names both figures, the
 # option, the identical header and the .svdx - four keyword checks - and says no.
 ('scaled-export', "opens with the answer: this file cannot settle it", """
**No. Nothing in this recording gets near 150.** The highest torque value in the file is 78.96, and
that conclusion holds whichever way the export was made. The header looks identical whether "Scale
values before export" was on or off, so the file cannot say which; the only way to get above 150
is 2 x 78.96 + 10 = 167.9, which is wrong in both cases. Send the .svdx to settle 79 or 34.
"""),
 ('scaled-export', "opens with the answer: this file cannot settle it", """
The recording does not show torque above 150 %. The peak is 79; a scaled reading of 168 is possible
but the column as it stands is the recorded figure.
"""),
 # Iteration 6: four of six answers, and the checks could not see it.
 ('needle-in-the-haystack', "does not list the axis's normal standstill creep as a defect", """
### 4. Clipped velocity

### 5. Whole run - `ActPos` creeps away from `SetPos` while `PosDiff` says it does not
"""),
 ('needle-in-the-haystack', "does not list the axis's normal standstill creep as a defect", """
5. **Whole run - the standstill offset between `SetPos` and `ActPos` creeps by about 0.07 units.**
"""),
 ('needle-in-the-haystack', "does not list the axis's normal standstill creep as a defect", """
## 3. Slow drift of ActPos away from SetPos, 0.078 units over the run
"""),
]


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

    for name, label, text in EXTRA_TRAPS:
        check = dict(CHECKS[name])[label]
        caught = not check(text, code_of(text), commands_of(text))
        lines.append(f"{name:28s} trap   {'caught' if caught else 'MISSED'}: {label}")
        if not caught:
            failures.append(f"{name}: extra trap passed '{label}'")

    for name, label, text in EXTRA_PASSES:
        check = dict(CHECKS[name])[label]
        ok = bool(check(text, code_of(text), commands_of(text)))
        lines.append(f"{name:28s} pass   {'passed' if ok else 'FAILED'}: {label}")
        if not ok:
            failures.append(f"{name}: real answer failed '{label}'")

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
