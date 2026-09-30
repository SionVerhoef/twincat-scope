# Field review -- main @ 49a8e9b

Run by an agent on the same commissioning workstation as the three rounds before (Windows 10,
decimal-comma locale, TwinCAT 3.1 build 4024.55, **Scope 3.4.3147.18**, the version Scope writes into
`ServerVersions` on save; Python 3.12.10). The subject: PRs #37-#40 on main at `49a8e9b`. The
skill was reinstalled from that commit.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; counts and
kinds are measured. Setpoints, positions and cycle times are confidential. Where a stroke
matters it is `L` (length) and `T` (time), and wall-clock times appear only as offsets. Index
groups are described, not given. Axes are `axis1`-`axis3` as in `field-review-c137eb9.md`.
Recordings stayed on the machine.

## Verdict

#38-#40 hold up on R3, with one miss:
- **axis3's ActPosModulo still reported `clipping`**, because a modulo channel that wraps onto
  its minimum looks as if it hit a rail at speed (K3, fixed in the patch).
- #40 turned **no** PosDiff ramp into a spike. It changed one SetAcc event, and that one is a
  command turning round, not a sharp peak.
- AxisState gained 507 steps. They are **real transitions the old code merged**, not over-firing.

The shipped templates open, lay out as documented, and fail as expected when recorded. Scope
upgrades their `Version` on save.

**`newscope`'s NC table puts ErrorCode on the axis, and on this NC it is in the axis's `ToPlc`
struct** (K1). Scope View's symbol browser lists the axis's real fields, and the table misses 11 of
them. Recorded by the browser's path, AxisState and ErrorCode read as sane `UINT32` values. `checkscope --tmc`
passed every case tried against a real `.tmc`. The target clock again leads the PC by about 10 min.

Tests: **324/324** on `49a8e9b` (`make_fixture`, `make_real_fixtures`, `test_verbs`; the
Windows-skipped checks skipped), and `evals/test_grader.py` passes. **325/325** with the patch.

## Setup: pass

All four setup commands pass. `test_grader.py` ends "grader separates good from trapped answers
on every eval."

## Part A -- `events` on R3

The same R3 as last round (600 s, 33 channels). "Before" is c137eb9 + the #38 changes (the
patch from the last round); "after" is 49a8e9b.

| Field | before | after (49a8e9b) | Expected |
|---|---|---|---|
| axis3.ActPosModulo | 332 hold, 650 step, 650 ramp, 1 clipping | 332 hold, **650 wrap**, 650 ramp, **1 clipping** | 650 wrap, 0 step, 0 clipping: **clipping remains** (K3) |
| axis1.SetPos | 655 hold, 1 156 ramp, 2 clipping | 655 hold, 1 156 ramp, **0 clipping** | ✅ |
| axis1.SetVelo | 652 hold, 1 806 ramp | same | -- |
| axis1.PosDiff | 1 414 ramp, 1 027 spike, 4 flatline, 2 step | **identical**; all 1 027 spikes `recurring: true` | ✅; #40 changed nothing here |
| PLC REAL64 | 2 clipping, 14 flatline, 11 step | same | ✅ unchanged |
| axis1.SetAcc | 333 hold, 3 367 ramp, 21 spike, 58 step | 22 spike, 57 step | one step → spike (#40) |
| axis2.AxisState | 1 041 step, 135 spike | **1 548 step**, 135 spike | not predicted; see below |
| one PLC INT16 | 605 spike, 52 step | 605 spike, 53 step | #40 |
| all | 20 861 | 21 367 | -- |

`command_channels` is unchanged: SetPos, SetVelo, SetAcc and axis3.ActPosModulo. axis3 has no
setpoint in R3 (only `ActPosModulo` is recorded for it), so #39's feedback-against-setpoint check
has nothing to compare against there. **No flatline carries `while_moving`**, which is consistent
with that.

**Time:** full `events` 1.93 s before, 1.82 s after; capped at 20, 1.44 s and 1.49 s.

**AxisState +507.** The axis cycles 0 → 4 → 3 → 5 → 0, and states 4 and 5 last one sample
each. The old code merged 3 → 5 → 0 into one step of −3, two samples wide. 49a8e9b reports it as
the two transitions it is, +2 and −5, and the 507 new events are exactly the −5s. The −1 into
state 3 is still absorbed into the +4 by both versions. So this is more faithful, not
over-firing. All AxisState steps are `recurring`.

**`--max-events 20`**, after:
- 6 flatlines (the PLC REAL64 four times, PosDiff twice), spread over the recording as the
  ranking promises, not first;
- clipping twice on the PLC REAL64, and **once on ActPosModulo** (K3). **No SetPos clipping.**
- **No PosDiff spike.** The recurring ones now rank after the one-offs.
- 9 one-sample integer steps on PLC `INT16` channels, and 1 step on the PLC REAL64. The INT16s
  look like sequence-step variables, and their step sizes differ, so they are not `recurring` (K4).
- 1 INT16 spike, **6 ms before PosDiff freezes** for its long flatline, and an INT16 step
  coinciding with a step on the PLC REAL64. Both are worth a look on a recording with a fault;
  here they are not defects.

**#40's reclassifications (three examples asked for; there are only two).**
1. SetAcc: a step became a spike 2 samples wide. The samples fall steadily to a point just short
   of zero and rise again in the same steps: a **command turning round**, not a sharp peak. On a
   command channel #40 makes this one false spike in 600 s.
2. A PLC INT16 goes from one step number to another for one sample, then to a third for 5
   samples, then to a fourth. Before, it was one spike 7 wide; now it is a step plus a spike
   6 wide. It is a state sequence, and neither reading is wrong.

No PosDiff ramp became a spike.

## Part B

**1. Templates as shipped: pass.**
- Both open. Each has one tab, and axis-diagnosis has the four stacked bands `templates/README.md`
  describes.
- **Recorded unedited**, axis-diagnosis says: *Error on connect channel: 'ActPos
  (MAIN.fbAxis.NcToPlc.ActPos)' Target not connected: '0.0.0.0.0.0 Port: 851'*.
- **With only the AmsNetId set** (5 elements, byte replacement): *Symbolname could not be found
  for channel: '"ActPos" (MAIN.fbAxis.NcToPlc.ActPos)'*. `checkscope --tmc` predicted this before
  recording: 0 of 5 resolved. Scope names only the first failing channel.
- **minimal-single-channel**, recorded: *Error on connect channel: 'Signal (PLACEHOLDER.Symbol)'
  Target not connected: '0.0.0.0.0.0 Port: 851'*. It fails on the NetId before it reaches
  `PLACEHOLDER.Symbol`, so Scope checks the connection first.
- **`Version` 1.0.0.0 was upgraded to 1.0.0.3 on save**, and `ServerVersions` 3.4.3147.18 was
  added. Scope also:
  - removed the 3 time-axis `AxisStyle` blocks (known: it keeps one per tab), 42 `IsFileBased`
    and `Suffix` elements, `IsTemplate` and `UseUserSettings`;
  - added unit blocks (`BaseUnitString`, `ScaleFactor`, `Offset`…) and series styles
    (`SeriesStyle`, `Antialias`, `MarkSize`…).

  The file stays UTF-8 with a BOM.
- An unchanged file is not rewritten by *Save*. Scope needs an edit before it writes.
- Note for testers: *Add Existing Item* **copies** the file into the Measurement project's own
  folder, and Scope saves that copy, not the file you picked.

**2. Windows fixes.**
- `ingest <real .svdx> -o C:\does\not\exist\x.parquet`: **pass.** `{"ok": false, "error":
  "cannot write …: the folder … does not exist", "fix": "Create the folder first, or write to one
  that exists."}`, exit 1.
- `doctor` reports the cache as `%LOCALAPPDATA%\tcscope\cache`: **pass**.
- The winget fix line on a machine without uv was **not re-run this round**. The last round's run
  on a machine without uv showed `winget install --id=astral-sh.uv -e`.

**3. `checkscope --tmc` against the real `.tmc`** (862 symbols): **pass.**
- A known-good `BOOL`, `INT` and `LREAL` resolve.
- A misspelled symbol: *"… is not in the compiled program, so Scope would report an unknown
  symbol."*
- A `DINT` declared `REAL64`: *"compiled as DINT, which Scope reads as INT32 (4 byte(s)), but the
  file says REAL64 (8 byte(s)). The recording would be of the wrong bytes."*
- Also: a member of an FB instance and a member two levels deep both resolve.
- An `Axes.*` symbol is left out of the check, correctly, because it is on port 501.
- An array element was not tried: no top-level scalar array was found.
- Nothing surprising about the reader.

**4. A UINT32 NC channel: pass, but not by the path `newscope` writes** (K1, K2).
- `newscope` with `Axes.<axis>.AxisState` and `Axes.<axis>.ErrorCode` types both as `UINT32`/4
  from the NC table, and `checkscope` passes it. Recording fails: *Symbolname could not be found
  for channel: '"ErrorCode" (Axes.<axis>.ErrorCode)'*.
- In R3, recorded with Scope View's own symbol browser, those two fields sit **one level
  deeper**, at `Axes.<axis>.ToPlc.<field>`: 4 segments, in a different index group from the
  3-segment direct fields such as `ActPos` and `ErrState`. The browser confirms that ErrorCode is
  not a direct axis field (K1).
- Given that 4-segment path, `newscope` **defaults both to `REAL64`** (reported as defaulted),
  because `nc_field_type` accepts only 3 segments.
- With the browser's path and an explicit `:UINT32`, the recording works: 49.9 s, 24 950 samples.
  `manifest` types them `UINT32`, and both read back as integers. They are **0 throughout**,
  because the axis stood still with no error. AxisState 0 is also R3's most common state. A
  recording with the axis moving would test more values.

**5. `correlate` on a broken multi-group export: not possible here.** No real export on this
machine has `cross_group_timing_valid: false`. The broken ones were among the 19 original
exports, which are gone.

**6. The 19 genuine exports: not possible here.** They are not on this machine.

**7. `tools/update-skill.ps1`: skipped.** v1.0.0 is not tagged; the repository has no tags.

## Part C

- **Subsave:** a Base licence here, and `checkscope` shows the licence warning on a Stop Subsave
  project (confirmed last round, and still present).
- **The export tool's `svdx=`** works as an alias of `svd=`.
- **`channellist=` with several names**, on R3's 33 channels:
  - names separated by **`;`** give exactly those channels (3 of 33);
  - **`,` and `|` are ignored without a word** (exit 0, all 33 channels);
  - names separated by spaces write **no file, with exit 0**.
- **`channel=` given twice** keeps only the last one.
- **Target clock:** the recording in item 4 ends 10 min 26 s after the PC-side stop time, the
  same lead as the last round (about 10 min). Timestamps in a recording are the target's.
- **Not reached:** an axis parked at a limit, a genuine saturation, *Scale values*, marker
  windows, Timelines All on a multi-channel group.

## Findings

### K1 -- `ErrorCode` is not an axis field; it is in `ToPlc` (not fixed)

Scope refuses `Axes.<axis>.ErrorCode` ("Symbolname could not be found"). Scope View's symbol
browser, opened on one axis of this NC, shows why. The axis's direct fields are:

| Type | Fields |
|---|---|
| `LREAL` (8) | ActAcc, ActPos, ActPosModulo, ActTorque, ActVelo, CtrlOutput, DriveOutput, PosDiff, PosDiffCouple, SetAcc, SetJerk, SetPos, SetPosModulo, SetTorque, SetVelo, TorqueOffset |
| `UDINT` (4) | AxisState, CmdNo, ControlDWord, CoupleState, ErrState, HomingState, OverrideV, StateDWord |
| structs | `FromPlc` (`MC.PLCTONC_AXIS_REF`, 128) and `ToPlc` (`MC.NCTOPLC_AXIS_REF`, 256) |

**There is no `ErrorCode` among them.** R3's ErrorCode and AxisState were recorded as
**`Axes.<axis>.ToPlc.<field>`**, the axis's copy of its NcToPlc struct. AxisState exists both
directly and in `ToPlc`; item 4 was refused only on ErrorCode, which fits. The browser shows IEC
type names (`LREAL`, `UDINT`), and the `.tcscopex` stores Scope's own (`REAL64`, `UINT32`). This
is one NC on TwinCAT 3.1 4024.55; whether other builds expose more at the axis level is unknown.

`NC_FIELD_TYPES` against that list:
- **Not direct axis fields, yet typed confidently:** `errorcode`, `errorid`, `position`. So
  `newscope` writes `Axes.<axis>.ErrorCode` as `UINT32` from the table (`type_source: nc-field`),
  and Scope cannot find it.
- **Missing from the table:** CmdNo, ControlDWord, HomingState, OverrideV, StateDWord (all
  `UDINT`, which would default to `REAL64`, the wrong width) and CtrlOutput, DriveOutput,
  PosDiffCouple, SetJerk, SetTorque, TorqueOffset (`LREAL`, where the default happens to be
  right).

Suggested:
- `newscope` should write ErrorCode, and optionally ErrorId, as `Axes.<axis>.ToPlc.<field>`;
- drop `errorcode`/`errorid`/`position` as direct fields, or warn on them;
- add the missing fields with their types.

### K2 -- the NC table does not type a 4-segment NC path (not fixed)

`nc_field_type` requires exactly `Axes.<axis>.<field>`. Given the browser's
`Axes.<axis>.ToPlc.<field>` it returns None, and the fields are defaulted to `REAL64` (8 bytes),
which would record the wrong bytes of a `UDINT`. The default is reported. Accepting
`Axes.<axis>.ToPlc.<field>` (and `FromPlc`), typed from `NCTOPLC_AXIS_REF`/`PLCTONC_AXIS_REF`,
fixes it together with K1.

### K3 -- an indexing axis's modulo rest was still clipping (fixed)

axis3 moves one turn at a time, so ActPosModulo reaches its minimum by **wrapping onto it at full
speed** and rests there 56% of the recording. #39 keeps clipping on a command channel when its
extreme is reached at speed, as a real saturation is. A wrap passes that test.

**Done:** a channel with `modulo` in its name is never reported as clipping, since its range ends
are wrap points. On R3, ActPosModulo's clipping is gone. The PLC REAL64's 2 clippings are
unchanged, and the "genuinely saturated signal still reports clipping" check still passes. One
regression check: an indexing-axis fixture (moves of exactly one period, all forward) fails on
49a8e9b with clipping at 92% and passes with the patch.

### K4 -- integer sequence variables take the capped slots (not fixed)

With PosDiff's recurring spikes ranked lower, 9 of the 20 capped slots go to one-sample steps
on PLC `INT16` sequence variables. They are routine state progression, not defects, and are not
`recurring` because their step sizes vary. Like AxisState's transitions, an integer state
channel's changes may deserve a descriptive kind (as a BOOL gets `transition`), rather than
`step`.

### K5 -- a command channel turning round can become a #40 spike (not fixed)

One SetAcc turnaround, a V just short of zero, is now a 2-sample spike. On a command channel the
ramps on either side already describe it. Exempting command channels from #40's no-plateau rule
would remove it. This is minor: once in 600 s.

### Tool arguments -- silent failures

`channellist=` with the wrong separator exports everything, and a space-separated list writes no
file. Both exit 0. That is worth a line in `references/export-tool.md` beside `start=`/`end=`.

## Still untested

- `doctor` on a machine without uv at this commit.
- `correlate` on a broken multi-group export, and the 19 genuine exports: neither is on this
  machine.
- `update-skill.ps1`: needs the v1.0.0 tag.
- An axis parked at a limit, a genuine saturation, *Scale values*, marker windows, Timelines All
  on a multi-channel group.
- Subsave (H3, H5), which needs a Professional licence.
- AxisState and ErrorCode with the axis moving.

Nothing was written to or activated on a controller. The user started and stopped every
recording. Only new files were added to a Measurement project, and only scratch copies were
changed.
