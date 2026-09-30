# Field review -- main @ c137eb9

Run by an agent on the same commissioning workstation as the 8bf9230 and 79660f4 rounds
(Windows 10, decimal-comma locale, TwinCAT 3.1 build 4024.55, Scope 3.4.3147.18 incl. the TF3300
export tool, Python 3.12.10). The subject: #34 (command channels, `hold`, defects ranked
first), with #29/#30/#32/#33 riding along. The skill was reinstalled from `c137eb9`.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; numbers are
measured. NC axis fields (`SetPos`, `ActPos`, …) are named because every NC axis has them. Axes
are `axis1`-`axis3`; axis1 is the one with the moves. The stroke's positions and duration are
setpoints, so they are given as `L` (stroke length) and `T` (stroke time), with times as
fractions of `T`; wall-clock times are given only as the offset between them. Recordings stayed
on the machine.

The material:
- **R3** (600 s, 33 channels, 5 time groups) for `events`.
- A scratch copy of a project, for the recording tests.
- A new 3-minute ring-buffer recording, **R4**.

## Verdict

#34 does what it set out to do for rests: every standstill on SetPos and SetVelo is now a
`hold` (655 and 652), none is a `flatline`, and a noisy channel that freezes is still a
`flatline`. But **it missed most moves** (J1). On a reciprocating axis most strokes go out and
straight back, and #34 kept a command ramp only if its run of change covered net distance.
SetPos gave 144 ramps for 1 156 legs, and SetVelo gave none. That is fixed in the patch.

The ActPos "1.76 ramps per move" behind bead zkl was **my miscount**: ActPos gives exactly one
ramp per leg, and the 656 "moves" of the last round were strokes of two legs.

Three things are described but not fixed:
- a clean feedback channel is classified as a command (J2);
- the following error's routine spikes fill the capped answer (J3);
- rest positions still clip, now on a command channel too (J4).

Subsave triggers cannot be tested on this machine, because they need a Professional licence
(J5, a warning is in the patch). The ring buffer behaves as `checkscope` now describes it.

Tests: **286/286** on `c137eb9` with `py -3 tests/test_verbs.py`; **294/294** with the patch.

## 1. `events` on R3

`command_channels`: **axis1.SetPos, axis1.SetVelo, axis1.SetAcc -- and axis3.ActPosModulo**, a
feedback channel (J2). No other feedback channel is in it: not ActPos, ActVelo or ActTorque.
`still_channels` is empty.

| Field | c137eb9 | with the patch |
|---|---|---|
| axis1.SetPos | 655 hold, **144 ramp**, 2 clipping | 655 hold, **1 156 ramp**, 2 clipping |
| axis1.SetVelo | 652 hold, **0 ramp** | 652 hold, **1 806 ramp** |
| axis1.SetAcc | 333 hold, 58 step, 21 spike | + 3 367 ramp |
| axis1.ActPos | 1 156 ramp | same |
| axis1.ActVelo | 1 806 ramp | same |
| axis1.PosDiff | 1 414 ramp, 1 027 spike, 4 flatline, 2 step | same |
| axis2.AxisState | 1 041 step, 135 spike | same |
| axis2.CoupleState | 435 transition | same |
| axis3.ActPosModulo | 332 hold, 650 step, 1 clipping | + 650 ramp |
| all | 14 026 events | 20 861 (+6 835 ramps) |

With the patch, SetPos's ramps equal ActPos's (1 156) and SetVelo's equal ActVelo's (1 806):
the clean command and its noisy feedback now describe the same motion identically.

**Flatlines left: 18.**
- **4 on axis1.PosDiff.** The longest, 228 s from 277.966 s, falls in a stretch where axis1
  reports no events at all. An exactly constant following error at standstill fits a disabled
  axis, not a frozen sensor.
- **14 on one PLC `REAL64`**, at 90-240 s each. They run through heavy motion (800 SetPos ramps
  inside the first). It is a PLC value that does not change, such as a parameter. That is not a
  defect, but "stopped updating" is the wrong word for it.

**`--max-events 20` (identical before and after the patch): routine, not defects.**

| Returned | What it is |
|---|---|
| 3 clipping | rest positions: SetPos at its minimum 63% of the time, axis3.ActPosModulo 56%, the PLC `REAL64` at its maximum 58% (J4) |
| 13 spike on PosDiff, 2.9-3.7 high, 26-30 samples wide | the following error's normal peak, alike on every stroke (J3) |
| 4 flatline | PosDiff 60 s at the start and the 228 s above; the PLC `REAL64` 40 s and 38 s |

R3 holds no known fault, so nothing real was missed. But on a recording that has one, 13 of 20
slots would be spent on routine following error.

## 2. Where a move gets split (bead zkl)

The first 10 SetPos segments. Times are from the segment start, as fractions of the stroke time
`T`; `w` is width in samples; `d` is the delta. Segments 1-3 are single-sample changes below any
display precision, not motion.

```
seg 1-3   n=1 each      SetPos: hold          ActPos: -      PosDiff: flatline w=77 / step w=1 d=+0.16
seg 4     one stroke of T, out by L and straight back
          SetPos  (c137eb9) hold +1.00T w=81                        <- no ramp
          ActPos  ramp +0.14T w=50 d=+L; ramp +0.64T w=50 d=-L
          PosDiff ramp +0.05T w=13 d=+2.08; ramp +0.16T w=37 d=-2.83; spike +0.51T w=13 d=+0.78;
                  ramp +0.66T w=39 d=+2.89; ramp +1.01T w=11 d=-1.26
seg 5-10  the same stroke, to within 0.05 in every PosDiff delta and 4 samples in every width
```

ActPos does not split a move. It reports one ramp per leg, covering the middle 50 of the leg's
~87 samples, where it moves fastest. The 1.76 of the last round was 1 156 ramps against 656
"moves" that were really 511 two-leg strokes and 144 one-way moves: 511 × 2 + 144 = 1 166
legs, against 1 156 ramps. Where the other 10 went was not traced. The split was in SetPos,
which with c137eb9 reported no ramp for two-leg strokes at all (J1).

## 3. Routine steps

**R3 does not show routine steps.**
- PosDiff has 2 steps in 600 s (Δ 0.157 and 0.155, at 6.196 s and 506.248 s).
- ActTorque is **identically 0** for all 600 s: one distinct value, so the drive does not feed
  it. `events` reports nothing for it, and nothing says so.

The routine events per stroke come out as ramps and spikes on PosDiff, with shoulders 11-41
samples wide, so they are wider than `--ramp-samples`:

| Stroke | PosDiff events per stroke | Mix |
|---|---|---|
| out-and-back (506) | 4 × 412, 5 × 94 | 2.37 ramps + 1.81 spikes |
| one-way (144) | 2 × 109, 3 × 35 | 1.49 ramps + 0.76 spikes |

Three examples, relative to the SetPos stroke (out 0-T/2, back T/2-T):
- ramp +0.05T (w 13, +2.08), as the move starts;
- spike +0.51T (w 13, +0.78), at the reversal;
- ramp +1.01T (w 11, −1.26), settling after the stop.

## 4. Recording tests

**4a and 4b, Subsave: not possible here.** Starting a recording with Start or Stop Subsave was
refused: *"A feature is denied: 'SubSaveTrigger'. A level of 'PROFESSIONAL_TRIAL' 'PROFESSIONAL'
is required; current level is 'BASE'. Activate a TE130X-license…"*. So on a Base-licence machine
a Subsave trigger does nothing, whatever the file says (J5). H3 and H5 need a machine with the
Professional licence.

**4c, ring buffer (R4): pass.** Record Time 60 s, Ringbuffer on (`StopMode ClientStop`), Set
Mark. It ran ~3 min and was stopped by hand.
- The export holds exactly **29 999 + 15 000 samples over 0-59.996 s**: Record Time at the
  default range, and nothing of the first 2 minutes.
- `checkscope` on the `.svdx` gives `ring_buffer: true`, `fixed_window: false`, and the
  ring-buffer advice.
- **The data ends at the stop, in target time.** The last sample is about 10 min 12 s later
  than the file's creation time by the workstation's clock, taken just after the stop. The 60 s
  recording from the last round shows the same ~9-10 min lead, so **timestamps in a recording
  come from the target's clock**, not the engineering PC's. Comparing a recording with a
  PC-side log needs that offset.

## Findings

### J1 -- a stroke that turns round gave no command ramp (fixed)

`cmd_events` took each run of non-zero first differences on a command channel as one candidate
ramp, and dropped it if `|col[e] − col[s]| < --min-step × span`. A reciprocating stroke has no
sample at rest at the far end, so out and back is one run that nets to zero. SetVelo's
triangular profile (up, down through zero, up) is one run as well.

**Done:** each run is split where the sign of its first difference changes, and each leg is
tested on its own. The effect on R3:
- SetPos 144 → 1 156 ramps and SetVelo 0 → 1 806, both equal to their feedback channels;
- holds unchanged;
- the top 20 unchanged, and 1.39 s against 1.37 s.

Checks were added to `command_channel_checks`, on a fixture whose reversal falls between
samples, as a real one does:

| Check | c137eb9 | patch |
|---|---|---|
| out-and-back stroke (trapezoid profile) = two SetPos ramps | 0 ramps: fails | 12 for 6 strokes |
| its SetVelo ramps three times per stroke | 18: passes (cruise breaks the run) | 18 |
| rests stay holds, never flatlines | passes | 7 holds |
| triangular profile (no cruise, as on R3): 3 SetVelo + 2 SetPos ramps per stroke | SetVelo 0, SetPos 6: fails | 18 and 12 |

### J2 -- a clean feedback channel is classified as a command (not fixed)

axis3.ActPosModulo moves without noise, so it is a command by the roughness test. Its standstills
become `hold` (332), which is the risk the command note names: a frozen sensor would read as a
setpoint at rest. Its modulo wrap-arounds are 650 `step` events (a defect kind) plus 650 ramps,
and it clips at its minimum 56% of the time.

Suggested:
- exclude NC `Act*` fields from `command_channels` by name, since the NC field table already
  knows them;
- report a jump of about one modulo period on a `*Modulo` channel as a wrap, not a step.

### J3 -- the following error's routine spikes fill the capped answer (not fixed)

PosDiff produces 1.81 spikes per out-and-back stroke, 1 027 in all, alike to within a few
percent. `spike` is a defect kind, so after #34 they take 13 of 20 slots.

Suggested: a spike that recurs at the same phase of nearly every command leg is routine. Ranking
by distance from the channel's own typical spike, rather than by absolute size, would push the
unusual one up.

### J4 -- rest positions still clip, now on a command channel (not fixed)

SetPos rests at its minimum 63% of the time and reports `clipping`, beside 655 `hold`s that
already say so. A command channel's extreme at rest is a rest position, not a rail. Exempt
command channels from clipping.

### J5 -- Subsave triggers need the Professional licence (warning added)

The licence is not in the file, so `checkscope` now warns on any enabled Start or Stop Subsave
group: "needs a TE130x Scope View Professional licence…". Four checks: a warning for each
Subsave action, and none for Start or Stop Record. The logic that counts Subsave as a recording
action is left alone: it can't be tested without the licence.

### Smaller observations

- An NC channel that is **identically 0** for a whole recording (ActTorque here) produces no
  event and no remark. A channel with one value for 600 s is worth saying so, because nobody
  records a signal they expect to be zero.
- `flatline` on a PLC value that is simply a constant parameter reads as a defect.

## Still untested

- H3 and H5 (Subsave), which need a Professional licence.
- 4.9: an axis parked at a limit, and a genuine saturation.
- *Scale values* on a scaled channel.
- Marker windows on a recording with markers.
- Timelines All on a group of several channels.
- `channellist=` with several names, and `svdx=`.

Nothing was written to or activated on a controller. Recordings were started and stopped by the
user in Scope View, and only a scratch copy of a project was changed.
