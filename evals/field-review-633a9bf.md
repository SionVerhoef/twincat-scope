# Field review -- main 633a9bf (round 2: verify the 74dd86d fixes)

Same commissioning workstation as `field-review-74dd86d.md`. Stand-ins as before; in addition
**axis2** is a second NC axis of the same machine. B1/B1b are the Part B axis. Production values,
state numbers and absolute positions are left out.

## Verdict

| § | Item | Verdict |
|---|---|---|
| 0 | Install main 633a9bf | PASS -- merges #57-#60 present; **359/359** (handoff said 362; the clone gives 359 too). Test counter gone from the program |
| 1 | `standing` on the settling tail (#57) | ❌ B1 still reports the same `standing` (7.312 s, 2.27 s). ✅ B1b unchanged: one, 13.244 s, 26.76 s |
| 2 | `recurring` (#58) | ✅ all 57 SetAcc steps `recurring` (32 + 25). SetAcc gone from the capped 20; nothing that replaced it is a defect |
| 3 | ToPlc tab (#59) | ✅ two tabs, `axis1` / `axis2`, no `ToPlc` tab; recorded, all six channels have data |
| 4 | Sub-cycle load (#60) | ⚠️ ST-a.tcscopex no longer exists. On a regenerated 1-tick stand-in: ✅ warning and `total_samples_per_second` 0 |
| 5 | Saturation (56p) | ⏭ No axis on this machine whose drive reports torque reaches its limit in normal work |

## §0 Install

- Clone: the 74dd86d review was stashed, then `git fetch && git checkout origin/main` →
  `633a9bf`. `git log --oneline -8` shows merges #57, #58, #59 and #60.
- The installed copy is not a git clone (earlier rounds put a `git archive` there), so it was
  backed up and a `git archive` of 633a9bf was extracted over it. No stale files remained apart
  from `.installed-from`, which was updated. `tcscope.py` is byte-identical to the clone's.
- `uv run tests/test_verbs.py`: **359/359 passed** in both the installed copy and the clone. The
  handoff expected 362; the gap is in the count, not the install.
- The test counter: not in the PLC sources, not in the compiled `.tmc`, not in the boot `.tmc`
  of port 851. Its name survives only in the editor's tree state.

*Note added on the development machine:* 362 was the count on each fix's own branch. Main at
633a9bf has 364 checks on Linux, and Windows runs five fewer, as in the rounds before: 359.

Not asked, seen once: the first `ingest` of R3's `.svdx` failed with "the export tool exited
cleanly but wrote no file", leaving an **empty directory** named after the target's stem in the
cache. The same command by hand worked in 8 s; a second `ingest`, unchanged, worked in 15 s and
the empty directory was gone. Not reproduced. If it recurs, a single retry in `ingest` would
cover it.

## §1 `standing` on the settling tail

All three recordings re-ingested from `.svdx` with 633a9bf.

- **B1b (end stop):** ✅ exactly one `standing` on PosDiff, setpoint SetPos, at **13.244 s**,
  13 378 samples = **26.76 s**, severity 26.756. Other kinds unchanged (41 ramp, 11 step, 5 hold,
  4 spike).
- **B1 (software limit):** ❌ **still one `standing`**, identical to last round: 7.312 s, 1137
  samples = 2.27 s, severity 2.274, value −0.031, rank 57 of 57.

Why #57 does not catch it: a run is the stretch where |PosDiff| ≥ `STANDING_FRACTION` × peak
(0.1 × 0.228 = 0.0228) while the setpoint rests. So the run **ends exactly where the decay
crosses that floor** -- at 9.586 s PosDiff is −0.0229 and keeps decaying afterwards. Inside the
run the last quarter cannot fall far below the floor, and B1's tail starts only ~1.5× above it:

| | median \|PosDiff\| |
|---|---|
| first quarter | 0.0341 |
| last quarter | 0.0250 |
| ratio | **0.73** (rule needs ≤ 0.5) |

PosDiff over the whole tail: 7.8 s −0.034, 8.8 s −0.029, 9.8 s −0.021, 10.8 s −0.015,
11.8 s −0.009. It is plainly decaying; the window the test looks at is just too short to show
half of it.

What separates the two real cases cleanly is **how the run ends**:
- B1: the run ends because |PosDiff| fell under the floor while the setpoint was still resting
  (the error went away by itself → settling).
- B1b: the run ends at 13.244 + 26.756 = **40.0 s, the end of the recording** (the error never
  went away).

So: "a run that ends by |PosDiff| dropping under the floor, with the setpoint still resting, is
settling" -- or apply the ratio test to the run extended past its end until the setpoint moves.

## §2 `recurring`

R3 full run: **27 380 events**, the same totals by kind as last round (transition 11 778, ramp
11 399, hold 1 972, spike 1 482, wrap 650, step 81, flatline 18).

axis1.SetAcc: 3 411 ramp, 333 hold, 57 step. **All 57 steps are `recurring`**: 32 one-sample +
25 two-sample. ✅ The other 24 steps in the recording (abort, rate, PosDiff) are not
`recurring`, which is right.

`--max-events 20`:

| # | kind | channel | t (s) | defect? |
|---|---|---|---|---|
| 1 | flatline (1 263) | rate REAL64 | −0.004 | no |
| 2 | flatline (3 019) | axis1.PosDiff | 0.0 | no: idle at start |
| 3 | step | rate REAL64 | 16.688 | **new** -- no: filtered rate updating |
| 4 | step | rate REAL64 | 23.216 | no |
| 5 | step | rate INT | 31.928 | no |
| 6 | step | rate REAL64 | 39.980 | **new** -- no |
| 7 | flatline (19 847) | rate REAL64 | 42.596 | no |
| 8 | step → abort | seq1 | 277.960 | no: the machine abort (real event) |
| 9-10 | step → abort | seq2, seq3 | 277.964 | **new** -- no: the same abort on the two other sequences |
| 11 | flatline (114 062) | axis1.PosDiff | 277.966 | no: idle after the stop |
| 12-14 | step → reset | seq1, seq2, seq3 | 277.980 | no: reset after the abort |
| 15 | flatline (19 013) | rate REAL64 | 280.772 | **new** -- no: rate standing still after the stop |
| 16 | flatline (77) | axis1.PosDiff | 506.092 | no |
| 17 | step | axis1.PosDiff | 506.248 | no: restart, first move |
| 18-19 | flatline | rate REAL64 | 508.940, 510.464 | no |
| 20 | step | rate REAL64 | 510.464 | no |

The five 2-wide SetAcc slots (#6-10 last round) are gone. They were replaced by two more
filtered-rate steps, the abort on seq2/seq3 (so the abort now shows on all three sequences,
both into and out of it), and one rate flatline after the stop. **0 of 20 are defects.** The
change is an improvement: the one real event now takes 6 slots instead of 4.

Minor, not investigated: event #1 is now reported at −0.004 s (0.0 last round); the group's
first timestamp in this export is −4 ms.

## §3 ToPlc tab

`newscope` from `axis-diagnosis.tcscopex`, channels `ActPos`, `ToPlc.AxisState`,
`ToPlc.ErrorCode` for axis1 and axis2, `--sample-time-ms 2` (the NC task is 2 ms),
`--record-time 15`. NC fields typed automatically (REAL64 / UINT32 / UINT32), all on 501.
`checkscope`: ok, 0 problems, 3000 samples/s `typical`, only the fixed-window warning.

Layout chosen and as Scope View shows it (Solution Explorer and the chart, after adding the file
to the Measurement project):

- DataPool: the six channels.
- Chart **axis1**: band *Position* (ActPos), band *Step / count* (AxisState, ErrorCode).
- Chart **axis2**: the same two bands with axis2's channels.
- **No `ToPlc` chart.** ✅ For contrast, a file generated in an earlier round, open in the same
  project, still shows its `ToPlc` chart -- the old layout.

Recording (pressed by the user): 7 150 rows, 14.298 s, 500 Hz on every group (2 ms written =
recorded), 0 gaps, `cross_group_timing_valid` true. All six channels have data:

| channel | span (max − min) |
|---|---|
| axis1.ActPos | 8.6·10⁻⁴ |
| axis1.AxisState / ErrorCode | 0 (constant 0) |
| axis2.ActPos | 4.9·10⁻⁵ |
| axis2.AxisState / ErrorCode | 0 (constant 0) |

Both axes were parked. AxisState 0 is credible: in R3 the same `ToPlc.AxisState` path on axis1
takes four values, with 0 the idle one (169 471 of 300 003 samples). The two flags are
constant, so this shows they resolve and are typed right, not that they follow a change.

Seen in Scope View, not a defect of the tool: on the axis2 tab the Position band auto-scales to
ActPos's 5·10⁻⁵ wobble, every value-axis label reads the same rounded value, and the trace is a
full-height square wave of encoder noise. In *Step / count* AxisState and ErrorCode lie on top of
each other at 0, so only one trace is visible.

Not explained: the `.svdx`'s embedded `RecordTime` is 143 000 000 (14.3 s), while the file
written and still on disk has 150 000 000 (15 s), and the toolbar showed 15 s. Either Record
Time was edited before this recording or it was stopped early; I did not see which.

## §4 Sub-cycle load

`ST-a.tcscopex` is no longer on disk (it went when the test scopes were moved out of the
project). `ST-A.svdx` holds only the snapped 40 000 / 20 000, not the 1 tick. So the item as
specified was **not run**.

Stand-in: `newscope` from `minimal-single-channel` with an LREAL PLC channel (851) and
axis1.SetPos (501), `--sample-time-ms 0.0001` → `BaseSampleTime` 1 on both. `checkscope`:

- warning: "2 acquisition(s) have a BaseSampleTime **under 50 us** (…). Scope silently records
  these at **one cycle of the task** that owns them, so they are left out of the load figure.
  BaseSampleTime is in 100 ns ticks - if 1 ms was meant, that is 10000." ✅
- `total_samples_per_second` **0.0**, not ~20 000 000. ✅
- `newscope`'s `sample_time_note` now states "rounds … down to a multiple of that cycle,
  minimum one cycle".

Small follow-up: with *only* sub-cycle channels the file reports load 0 and `load_band`
`typical`. Without knowing the task cycle that is the honest choice, but the real load is at
least one sample per cycle per channel (here it was 250 + 500/s); the band could say "unknown"
rather than `typical`.

## §5 Saturation

Not run: no axis on this machine whose drive reports torque reaches its limit in normal work.
B2 / 56p stays open.

## For the beads

- **edp.7 (§1):** ❌ not fixed on real data. B1's settling tail is still reported, unchanged. The
  quarter-ratio test looks only inside the run, and the run is cut off where |PosDiff| crosses
  10 % of peak, so a real tail starting near that floor gives 0.73, never ≤ 0.5. Suggested
  criterion: a run that ends by the error dropping under the floor while the setpoint still
  rests is settling (B1); one that ends at the recording's end or when the setpoint moves is
  standing (B1b ends at 40.0 s = end of recording). Add B1's shape as a fixture: a tail that
  starts ~1.5× the floor and decays through it.
- **edp.8 (§2):** ✅ 57/57 SetAcc steps `recurring`. The capped 20 lost SetAcc and gained two
  rate steps, the abort on seq2/seq3 and one rate flatline; 0 of 20 are defects.
- **edp.5 (§3):** ✅ two tabs named after the axes, no `ToPlc` tab, as Scope View shows it, and
  a recording with all six channels. Flags constant (axes parked), so value changes were not
  observed on this path this round; R3 covers that.
- **edp.6 (§4):** ✅ on a regenerated stand-in, not on ST-a itself: warning present, load 0.
  Optional: `load_band` "unknown" instead of `typical` when every channel is sub-cycle.
- **56p (§5):** not run: no axis with a torque-reporting drive reaches its limit in normal work.
  Still open.
- Not on a bead: the export tool once exited 0 without writing the CSV for R3 (empty directory
  left in the cache); the immediate retry worked. Consider one retry in `ingest`.
