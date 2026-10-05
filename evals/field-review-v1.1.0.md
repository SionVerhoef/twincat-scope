# Field review -- v1.1.0 (round 3: confirm the settling fix)

Same commissioning workstation and stand-ins as `field-review-633a9bf.md` (axis1/axis2, B1, B1b,
R3). Names are stand-ins, numbers are real. No new recording for §1-§2.

## Verdict

| § | Item | Verdict |
|---|---|---|
| 0 | Install v1.1.0 | PASS -- "Installed twincat-scope v1.1.0", doctor clean, **362/362** |
| 1 | Settling tail vs standing (edp.7) | ✅ B1: no `standing`. ✅ B1b: exactly one, 13.244 s, 13 378 samples, 26.756 |
| 2 | R3 regression | ✅ 27 380 events, totals identical, no `standing`; capped 20 identical to round 2, 0 defects |
| 3a | 1-tick load (#63) | ✅ "under 50 us" warning, `total_samples_per_second` 0.0, `load_band` "unknown" |
| 3b | Scaled CSV warning (#65) | ✅ warning names the channel and says "give both readings until the export setting is known". Scale values **off**. CSV = `.svdx`, raw, value for value |
| 4 | Housekeeping | ✅ see §4 |
| 5 | Empty-export watch | Not seen: four `.svdx` ingests, all first time |

## §0 Install

- The clone's 633a9bf review was stashed (`field-review-633a9bf (delivered as patch)`) and the
  clone checked out at tag `v1.1.0` → `34f94a4`.
- The old installed copy (a git archive of 633a9bf, with its `.installed-from`) was backed up
  outside the target first. `tools/update-skill.ps1 -Target <same folder as before>`, no
  `-Version`, printed "Looking up latest release… Downloading v1.1.0… Replacing existing …
  Installed twincat-scope v1.1.0 into …".
- The release zip writes no `.installed-from`; the target now holds only the release's files.
  Compared with the tag's tree ignoring line endings: identical.
- `tcscope.py doctor`: every check ok (export tool found, cache directory present).
- `uv run tests/test_verbs.py` in the installed copy: **362/362 passed** (Windows).

## §1 Settling tail vs standing

Both re-ingested from `.svdx` with v1.1.0 (20 000 rows, 6 channels each), then
`events --max-events 1000`.

- **B1 (software limit):** ✅ **no `standing`.** 56 events: 41 ramp, 7 spike, 5 hold, 3 step.
  Round 2 reported 57 with the `standing` ranked 57th, so nothing else changed. Items a-e
  therefore not needed.
- **B1b (end stop):** ✅ exactly one `standing` on PosDiff, setpoint SetPos, at **13.244 s**,
  **13 378 samples** = 26.76 s, severity **26.756**. Other kinds unchanged: 41 ramp, 11 step,
  5 hold, 4 spike (62 in all).

## §2 R3 regression

R3 re-ingested from its `.svdx` with v1.1.0 (300 003 rows, 33 channels, 17 s), then `events`
uncapped: **27 380 events**, not truncated, **no `standing`**. By kind: transition 11 778,
ramp 11 399, hold 1 972, spike 1 482, wrap 650, step 81, flatline 18 -- identical to round 2.

`--max-events 20`: the same 20 as round 2 §2, same order, kinds, channels and times (rate
flatlines and steps, the idle PosDiff flatlines, the abort and reset on all three sequences at
277.96-277.98 s, the restart at 506 s). **0 of 20 are defects.** Event #1 is still at −0.004 s
(the group's first timestamp in the export).

## §3a 1-tick stand-in

`newscope` from `minimal-single-channel`, one LREAL PLC channel plus axis1.SetPos,
`--sample-time-ms 0.0001`. `checkscope`: ok, no problems, and

- warning: "2 acquisition(s) have a BaseSampleTime under 50 us (…). Scope silently records these
  at one cycle of the task that owns them, so they are left out of the load figure. …" ✅
- `total_samples_per_second` **0.0** ✅
- `load_band` **"unknown"** ✅ (round 2: "typical")

Same result as on the other workstation.

## §3b Scaled CSV

Stand-in: `newscope` from `axis-diagnosis`, axis1 ActPos, SetPos and PosDiff on 501, 2 ms,
`--record-time 10`; `checkscope` ok, 0 problems, 1 500 samples/s. Recorded by the user on the
parked axis, saved as `.svdx` first. Then, in Scope View, ActPos given **Scale Factor 2,
Offset 10**, exported to CSV with the Full header and **"Scale values before export" off**.

The CSV header shows `Offset;10;0;0` and `ScaleFactor;2;1;1` (ActPos, SetPos, PosDiff).

`manifest` on the CSV (`;` / `,`, 5 101 rows, 10.2 s, 500 Hz, 0 gaps): one warning, naming the
channel:

> ActPos: a scale factor/offset is set (scale_factor/scale_offset). … give both readings until
> the export setting is known. …

✅ ActPos carries `scale_factor` 2.0 and `scale_offset` 10.0. SetPos and PosDiff carry no
scaling and get no warning.

Both ways, compared (`ingest` of the same recording's `.svdx`, 5 100 rows, 10.198 s):

- The values are **raw** in both: ActPos sits at the parked position ± 4·10⁻⁴ in both, not at
  2 × that + 10. So with the setting off, the CSV's reading as it stands is the true one, and
  factor × value + offset would have been wrong. That is what the warning tells you to check.
- They are identical **value for value, with a shift of one sample**: CSV sample *i* equals
  `.svdx` sample *i − 1* for all 5 100 pairs (max difference 0). At lag 0 only 1 610 of 5 100
  match (encoder noise). The Scope View CSV has one extra sample at the start (5 101 vs 5 100
  rows), so the same physical sample is 2 ms later in the CSV than in the `.svdx` ingest.
  I did not look at which of the two starts where Record started.

Seen in passing, not on a bead: `manifest` reports the one header `Offset` row twice, as
`display_offset` 10.0 and as `scale_offset` 10.0. SKILL.md says a `display_offset` "is where a
trace was drawn -- never add it to the values", while the warning says to apply
factor × value + offset. Same number, opposite advice. Here the offset was set as the channel's
scaling, so `scale_offset` is the right name. Consider dropping `display_offset` when it equals
`scale_offset`, or changing the SKILL.md sentence.

## §4 Housekeeping

- `ToPlc-tabs.tcscopex` was on disk in this machine's Measurement project folder but **not
  listed in the `.tcmproj`** (untracked in the project's git too). Moved out of the folder to
  the field-scopes archive; not deleted.
- The 1-tick stand-in was only ever in a scratch folder; deleted.
- The scaled stand-in `.tcscopex` was deleted from the project folder after the check (it never
  reached the saved `.tcmproj`). Its recording (`.svdx` and the scaled CSV) stays in the
  field-scopes archive with the other round recordings.

## §5 Empty-export watch

Not seen. B1, B1b, R3 and the §3b recording each ingested on the first try (R3 in 17 s); no
empty directory was left in the cache.

## For the beads

- **edp.7 (§1):** ✅ fixed on real data. B1's settling tail is no longer `standing`; B1b's end
  stop still is, with the same start, length and severity. Can close.
- **§2:** no regression on R3 -- totals and the capped 20 identical to round 2.
- **#63 (§3a):** ✅ `load_band` "unknown" when every channel is sub-cycle.
- **#65 (§3b):** ✅ the warning fires on a real Scope View export, names the channel, and has the
  "give both readings" text. Scale values was off; CSV and `.svdx` are both raw and identical,
  one sample apart. Small follow-ups: the CSV has one leading sample more than the `.svdx`
  ingest; and `display_offset` versus `scale_offset` on the same header row give opposite advice.
- **Retry (§5):** nothing to add; the failure did not recur here.
