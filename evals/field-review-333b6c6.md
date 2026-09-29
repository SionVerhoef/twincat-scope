# Field review -- main @ 333b6c6 (last round before v1.0.0)

Run by an agent on the same commissioning workstation as the rounds before (Windows 10, Dutch
locale, TwinCAT 3.1 build 4024.55, **TwinCAT Measurement / Scope View 3.4.3147.18** per its About
box, Python 3.12.10). The subject: PRs #41-#44 on main at `333b6c6`. The skill was reinstalled from
that commit.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced. Index groups and
offsets are described, never given. Setpoints, positions and cycle times are left out, and
wall-clock times appear only as offsets. Axes are `axis1`-`axis3` as in the reviews before.
Recordings stayed on the machine.

## Verdict -- release blockers

| Item | Result | Blocker? |
|---|---|---|
| Setup | ✅ 337/337 on Windows (Linux 342; the same 5 skipped), grader passes | -- |
| Part A -- ActPosModulo, AxisState, two-valued integers, unchanged channels, time | ✅ as expected | no |
| **Part A -- integer state channels (L1)** | ❌ on 333b6c6: changes a few samples apart are merged into one `ramp` or `spike`, losing the state between, and the merged ones are never `recurring`. **Fixed in the patch**, with a regression check. | **yes on 333b6c6, cleared by the patch** |
| Part A -- capped 20 | ⚠️ the expectation "no INT16 sequence steps" is not met. The INT16 slots are rare, genuine state pairs, not routine ones. A design question, not a defect. | no (judgement) |
| **Part B -- NC paths from `newscope`** | ✅ every path typed `nc-field` as expected, recorded without an error, types kept, values plausible; the old path is caught | no |
| **C3 -- scaled channels (M1)** | ❌ on 333b6c6: a Scope View CSV exported with *Scale values* on is **indistinguishable** from a raw one, and was read as raw with no warning. `ingest` of the `.svdx` is not affected. **Fixed in the patch** (reported, and a CSV warning), with regression checks. | **yes on 333b6c6, cleared by the patch** |
| C4 -- marker windows | ✅ no marker data in the export; the reader is unaffected | no |
| C5 -- Timelines All, multi-channel group | ✅ read correctly | no |
| C1 -- `doctor` without uv | ✅ the uv fix line is exactly `winget install --id=astral-sh.uv -e`, and the cache is `%LOCALAPPDATA%\tcscope\cache` | no |
| C2 -- parked at a limit, genuine saturation | ⏸ **deferred past v1.0.0**; a bead is proposed below | no |

Tests: **337/337** on `333b6c6`; **343/343** with the patch.

## Part A -- `events` on R3

The same 600 s, 33-channel recording. "49a8e9b" is last round's "after" column (#41 had not
merged then).

| Field | 49a8e9b | 333b6c6 | with the patch | vs expected |
|---|---|---|---|---|
| axis3.ActPosModulo | 332 hold, 650 wrap, 650 ramp, 1 clipping | 332 hold, 650 wrap, 650 ramp, **0 clipping** | same | ✅ |
| axis2.AxisState | 1 548 step, 135 spike | 2 064 step, 135 spike | **2 603 step** | ✅ more, now including the −1 into state 3; all from/to; 2 602 of 2 603 recurring |
| PLC INT16 sequences (#17, #18, #19) | e.g. 605 spike, 53 step | e.g. 5 ramp, 605 spike, 536 step | e.g. **3 269 step** | ✅ with the patch; 99.4-99.96% recurring |
| two-valued declared integers | axis2.CoupleState 435 transition | **435 step** | same | ✅ the only such channel |
| SetPos, SetVelo, PosDiff, PLC REAL64 | -- | unchanged | unchanged | ✅ |
| all | 21 367 | 23 806 | 27 360 | -- |

**Time:** full run 1.84-1.97 s on 333b6c6 and 1.85-1.92 s with the patch. Capped at 20:
1.48-1.56 s. Under the ~2 s mark.

On 333b6c6 every event on an integer state channel carries `from`/`to`. But the 85 `ramp`s on
INT16 sequence variables were all one-offs, among them **72 alike `320 → 332`**, and a ramp is never
`recurring` (see L1).

**Three non-recurring integer events (with the patch):**
1. **Three sequence variables jump to their abort state at the same sample**, each pair seen once,
   14 ms after PosDiff freezes for 228 s. This is the machine stopping. **Genuine one-off.**
2. **Sequence start**, seen twice, then one-off branch pairs: once after power-up and once after
   the long idle. **Genuine**: the machine started twice.
3. **A branch on one sequence variable taken 10×** in 600 s. It is real but regular, and falls
   below the 20-alike threshold. **Borderline.**

### The capped 20 (with the patch)

| Slots | What |
|---|---|
| 14 | INT16 steps with rare state pairs: sequence start (twice, with its first branches), the stop (three variables), the regular branch above (4) |
| 2 | clipping on a PLC `REAL64` that is a parameter sitting at its two values |
| 2 | flatlines: that parameter, and the following error while the axis was idle |
| 2 | SetAcc steps, routine on a command channel |

No ActPosModulo clipping ✅.

**Why the INT16s win.** A state change is a `step`, which is a defect kind. Its severity is its size
divided by half the channel's smallest change, so a sequence jump scores 180-1 280, against about 3
for a real analogue fault. The one-off rule removes the routine pairs, but not rare-yet-normal ones
such as the sequence start. The stop slot is exactly what a fault diagnosis wants. The risk is that
a small cap on a recording with one analogue fault and several rare state pairs pushes the fault
out.

Options:
1. accept it and document it;
2. a separate descriptive kind for state changes, kept a defect only on error-code-like channels
   (sitting at 0, rarely non-zero);
3. score a state change by its rarity rather than its size;
4. at most N slots per channel.

Option 2 is suggested.

## Part B -- NC paths from `newscope`: pass

One file on axis1:

| Path | `newscope` type (`type_source`) | recorded | `manifest` type | values, ~30 s with the axis moving |
|---|---|---|---|---|
| `ToPlc.ErrorCode` | UINT32 (nc-field) | ✅ | UINT32 | 0 throughout (no error) |
| `ToPlc.AxisState` | UINT32 (nc-field) | ✅ | UINT32 | **changes while moving**: 40 transitions through 4 states |
| `ToPlc.CmdNo` | **UINT16** (nc-field) | ✅ | UINT16 | whole numbers, **identical sample for sample to the direct `CmdNo`** |
| `ToPlc.ModuloActTurns` | **INT32** (nc-field) | ✅ | INT32 | 0 (not a modulo axis) |
| `HomingState` | UINT32 (nc-field) | ✅ | UINT32 | 0 |
| `CmdNo` | UINT32 (nc-field) | ✅ | UINT32 | whole numbers |
| `SetJerk` | REAL64 (nc-field) | ✅ | REAL64 | plausible |
| `FromPlc.Override` | UINT32 (nc-field) | ✅ | UINT32 | 100% (in its own units) on every moving sample, 0 only while idle |
| `ActPos`, `SetPos` | REAL64 (nc-field) | ✅ | REAL64 | plausible |

Scope View reported no error, and in particular no "Symbolname could not be found". `checkscope`:
ok, no problems.

**The old path**, `Axes.<axis>.ErrorCode`:
- `newscope` gives `nc_paths_suspect: {Axes.<axis>.ErrorCode: Axes.<axis>.ToPlc.ErrorCode}`, and
  types it as a reported `REAL64` default;
- `checkscope` warns: *"not a field of the axis, so Scope may report it as an unknown symbol - it
  is a member of the axis's ToPlc struct, Axes.<axis>.ToPlc.ErrorCode."* ✅

## Part C

**C3 -- scaled channels (M1).** Scope View's display scaling (factor and offset on a channel) was
tested through every route on one recording, with ActPos scaled by factor 2 and offset 10:

| Route | Header shows | Values |
|---|---|---|
| **`ingest` on the `.svdx`** (export tool, no `config=`) | ScaleFactor 2, Offset 10 | **raw** |
| export tool, `config=` with `ScaleValues` True | same | factor × raw + offset |
| Scope View, *Scale values* **off** | same | raw |
| Scope View, *Scale values* **on** | same | factor × raw + offset |
| Scope View, *Scale values* on, factor 1 / offset 0 | ScaleFactor 1, Offset 0 | raw (no change) |
| Scope View, *Scale values* off, offset only | Offset 10 | raw |
| Scope View, *Scale values* on, an offset on one channel and factor 10 on a `UINT32` | as set | offset applied on its own; the integer becomes 10 × raw and stays whole |

So:
- the header is **identical** whether or not the values were scaled;
- the file does not record the option;
- `manifest` reports the Offset row as `display_offset` ("never add it") and ignores ScaleFactor.

A hand export with *Scale values* on is therefore read as raw, and silently off by factor and
offset. `ingest` on the `.svdx` is safe, because the tool exports raw by default. See M1 for the
fix.

**C4 -- marker windows.** With a marker window added to the chart, the export contains no marker
rows at all, and the reader reads it normally. Whether choosing the window in the dialog's *Marker
Windows* list adds a table was not confirmed: the list offered nothing to select.

**C5 -- Timelines All on a 10-channel group.** 20 columns, each channel with its own time column.
`manifest` reads all 10 channels and merges the identical time columns into one group of 16 322
samples, with no malformed rows and no backsteps. Read correctly, not refused.

**C1 -- `doctor` without uv: pass.** Run on a second Windows 10 22H2 PC, at `333b6c6`:
- The uv check prints `winget install --id=astral-sh.uv -e   (no admin rights needed)`.
- The cache directory is `%LOCALAPPDATA%\tcscope\cache`.
- TwinCAT is installed there, so the export-tool check passed.
- Step 3 (installing uv) was not repeated; the 8bf9230 round had already shown `ok: true` with
  only the export tool missing.

That PC first had **no Python at all**: `py` was not on PATH, and `python.exe`/`python3.exe` were
0-byte Microsoft Store stubs. So `doctor` could not be reached until Python was installed for the
user (3.12.10, which does not bring uv).

- **Documentation point:** `doctor` needs no third-party packages, but it does need Python.
  `README.md` could say so, with the per-user install line.
- The agent there accepted winget's source terms (`--accept-source-agreements`) without asking.
  That is a process note, not a skill finding.

**C2 -- an axis parked at a software limit, and a genuine saturation:** deferred past v1.0.0, see
the bead below.

## Findings

### L1 -- close changes on an integer state channel were merged (fixed)

#43 lowered the detection threshold on integer state channels so that every change counts, but
still ran the changes through the analogue excursion logic. That logic joins over-threshold
differences a few samples apart. So `100 → 101 → 140`, with state 101 held for two samples, came
back as one `ramp 100 → 140`. The state between was lost, and a ramp is descriptive, so it was
never `recurring`: 72 alike on one sequence variable, all one-offs. Close changes within the spike
width became spikes instead.

**Done:** on a state channel each change of value is its own `step` with `from`/`to`, and the
excursion logic is skipped. The check is in `integer_sequence_checks`: a `Burst` channel that goes
100 → 101 (2 samples) → 140 every cycle.
- on 333b6c6 it gives `100 → 140` and `140 → 100` only;
- with the patch it gives all three pairs, every one a `step`, all `recurring`.

On R3, the INT16 sequence variables now carry only steps, 99.4-99.96% recurring. AxisState has all
2 603 transitions.

### M1 -- a Scope View CSV with *Scale values* on was read as raw (fixed)

See C3. This was a quiet wrong number of the kind the skill exists to catch: the values were off by
the display factor and offset, with no warning. It is confined to hand exports made with the
option on.

**Done:**
- The header's `ScaleFactor` row is read beside `Offset`, and both survive Parquet.
- `manifest` reports `scale_factor` and `scale_offset` on every channel whose scaling is not
  1 / 0.
- For data that did not come from a `.svdx` (a CSV, or a Parquet ingested from one), it warns:
  *"display scaling is set… If this CSV was exported from Scope View with 'Scale values before
  export' on, these values are factor * raw + offset, not raw - the file does not record which.
  Re-export with that option off, or ingest the .svdx…"*.
- `ingest` records whether its input was a `.svdx`, and the Parquet layout keeps that as
  `origin`.

On the real exports of this round:

| Export | Warning |
|---|---|
| `ingest` of the scaled `.svdx` | none (scaling reported, values raw) |
| Scope View CSVs with scaling set, raw or scaled | yes, on the scaled channels only |
| factor 1 / offset 0 | none |
| R3 | none |

**Left open:** a Scope View export with the default **Name-only** header has no ScaleFactor or
Offset rows, so a scaled one cannot be detected at all. `references/export-tool.md` now says so
beside the Full-header advice.

Regression checks (`scale_checks`), on the real two-rate fixture with ActPos given factor 2 /
offset 10:
- the scaling is reported, and only on that channel;
- the warning fires and names only ActPos;
- the untouched fixture gives no warning;
- both survive `ingest` of the CSV.

The first two and the last fail on 333b6c6.

### Smaller

- Of the capped 20, 6 slots go to things that are not defects: 2 routine SetAcc steps, the
  parameter's 2 clippings and its flatline, and the following error at an idle axis. None is new.
- `doctor` on a PC without Python: see C1.

## Bead for after v1.0.0 -- C2

To store as a bead: **"Field-test clipping on an axis parked at a software limit and on a genuine
saturation."**
- Record ~30 s of an axis moved to, and left at, a software limit, and of a channel that really
  saturates while moving (a torque or following-error limit).
- Expected: `events` reports `clipping` for the saturation and not for the parked axis.
- Open since the first field round (brief 4.9). No machine state for it was available in any
  round.

## Still untested

- C2 (the bead above);
- Subsave with a Professional licence;
- `correlate` on a broken multi-group export;
- the 19 original exports;
- `update-skill.ps1` (it runs after the v1.0.0 tag).

Nothing was written to or activated on a controller. The user started and stopped every recording
and moved the axis. Only new files were added to a Measurement project.
