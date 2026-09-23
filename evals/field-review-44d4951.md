# Field review — `44d4951`, round 7: still axes, held steps, and a re-save

The same test workstation as the earlier reviews, on 2026-09-23, running main at `44d4951`.
Nothing was commanded: normal operation was recorded, and a person pressed Record.

**Anonymised.** Channels are named by role; no NetID, project, product or symbol path is
here. Counts, rates, ranges, fractions and severities are as measured. The recordings stay on
the machine.

This covers the addendum to round 7 — the parked axis (§4.9) and the re-save check. The
round-7 report's own item 1 was not passed on here beyond its conclusion: that Scope View's
CSV export still read as 41 channels, not 40.

## Re-save keeps 8 ms: PASS

Scope View re-saved the 8 ms file after a harmless change (321 632 → 441 044 bytes).
`BaseSampleTime` stayed 80000 on all 40 acquisitions and `Offset` 0 on all 42 display channels.

## The recording

48.7 s at 125 Hz, 6 090 samples per channel, from the 8 ms file. Read two ways, with identical
`stats` and `events`: the `.svdx` through `ingest` (40 channels, copies collapsed on symbol),
and Scope View's own CSV export (41 channels — one copy survived). The operator's note: actual
positions always jitter by a few micrometres; set positions are exactly constant.

Positions are PLC `LREAL`s in mm; the quantisation step was 2.47e-5 mm on every one.

| Channel (role) | Behaviour | Range | `pct_at_max` | `pct_at_min` | Clipping |
|---|---|---|---|---|---|
| track A, axis 1 position | moved 299.9 → 688.9, then parked | 389 mm | 0.033 | 0.016 | 0 |
| track A, row advance (derived) | moved, then parked | 2 304 mm | 0.016 | 0.016 | 0 |
| track A, axis 2 position | still, dither only (80 levels) | 1.95 µm | 0.460 | 11.133 | 1 — min, fraction 0.111, severity 11.1 |
| track B, axis 1 position | still, dither only (55 levels) | 1.33 µm | 0.164 | 1.002 | 1 — min, 0.010, severity 1.0 |
| track B, axis 2 position | still, dither only (49 levels) | 1.19 µm | 0.016 | 0.082 | 0 |
| track B, row advance (derived) | still, dither only | 1.33 µm | 0.164 | 1.002 | 1 — min, 0.010, severity 1.0 |
| virtual axis `ActPos` | exactly constant | 0 | 100 | 100 | 0 (constant) |

No NC `ActVelo` was in the file, and no genuinely saturating channel was available.

## Findings

1. **Moved and then parked did not clip.** The parked value was not the recording's exact
   extreme: the axis settled a few micrometres off its peak, and 0.0 % of the last 30 % of
   samples sat at max or min. It drew 6 flatline events instead.
2. **Standing still did.** Three of four still actual positions clipped at 1–11 %, over a
   whole range of 1–2 µm — 49 to 80 quantisation levels. Exactly constant channels were fine.
3. **Same cause, steps.** All four still positions reported a "step" of 0.6–1.6 µm at one
   instant, 11.854 s, severity 5.5–13.7: `--min-step` floors the threshold at 1 % of the
   channel's own travel, which for a still channel is about a micrometre. A real,
   simultaneous correction — not one anyone wants ranked.
4. **Held steps clipped hardest.** Across all channels, 45 events, 8 of them clipping on 6
   channels, 5 of the 8 on step enums held at one step: the sequencer's step at its max
   (fraction 0.241, severity 24.1), the track steps at 200 (0.734, severity 73.4) and at 10
   (0.241, severity 24.1). The highest severities in the recording.

## What was done with it

- A real-valued channel spanning fewer than 100 of its own quantisation steps is treated as
  still: no clipping or step for it, and `events` names it under `still_channels`.
- Integer channels are exempt from clipping and flatline, as bits were.
- Copies in Scope View's own export are matched in any column order.

## Not covered

An axis parked exactly at a hard or software limit; a genuine current-limit saturation. §4.10
(Copilot) was skipped by the user; Part B needs the 19 exports, which are not on this machine.
