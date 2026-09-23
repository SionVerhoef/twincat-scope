# Field review — `6872161`, round 6: the reader re-run, and flag lanes rejected

The same test workstation as the earlier reviews, on 2026-09-23, running main at `6872161`
(PR #17: exported copies collapsed on read, `display_offset` reported, flags drawn in lanes).
A plain copy, checked by `newscope` printing `sample_time_note`. A person pressed Record;
nothing was written to the machine.

**Anonymised.** Names are stand-ins; no NetID, project, product or symbol path is here.
Counts, rates, sizes and times are as measured.

## Verdict

The new reader did what it was built for on real recordings. The flag lanes did not: the user
found them harder to read and asked for flags on 0/1. A second CSV layout turned up — Scope
View's own export — in which copies could not be matched by symbol.

## 1 — round 5's recordings, re-read: PASS

| | Channels | Groups | Rows | Duration |
|---|---|---|---|---|
| R1 | 40 (was 42) | 40 | 5 637 | 45.09 s |
| R2 | 40 (was 42) | 40 | 1 940 | 15.51 s |

`copies_collapsed` in both: the parent step kept, `(1)` and `(2)` dropped. Checked name by name
against the old 42-column export: no other channel lost. R2's offset flag: `display_offset` 2,
`stats` min 0, max 1.0, n 1 940 — the offset not added. R2's parent step: `events` reported two
transitions, 10 → 0 at 7.742 s and 0 → 10 at 12.262 s, both real and each reported once.

## 2 — regenerated at 8 ms, recorded, exported

`newscope --sample-time-ms 8`: 40 acquisitions, `BaseSampleTime` 80000 on all. `checkscope`
`ok`, `acquisitions_in_several_tabs` 1, load typical, one warning (fixed window). Adding the file
to the project did not make Scope rewrite it (same size, 321 632 bytes, same timestamp), so a
re-save of 80000 was **not tested**; the recording ran at 8 ms / 125 Hz measured, so there was
no snap at 8 ms on a 4 ms task.

Export through `ingest`: 10.6 s, 1 326 samples per channel, 40 channels, 12 changing.
`copies_collapsed` present. `display_offset` on all 9 lane flags — 1.5 to 10.5 in the 8-flag
tab, 1.5 in each 2-flag tab — the lane-0 flags carrying none. Flag values stayed 0/1.

**Flag lanes: rejected.** In the user's words, "Unclear to read. Better to keep everything on 0
and 1." A flag high in lane 0 is drawn at 1.0, half a unit below the next lane's 0, so which
lane a trace belongs to — and whether it is high — cannot be read; the axis labels (0, 2, 4, …
12) do not line up with the lanes. Reverted.

### Scope View's own CSV export

A CSV exported by hand from Scope View, of another, idle 7.06 s recording, has a different
layout: comma delimiter, dot decimal, a preamble of name, file, start and end time, then a row
of names over **one shared time column** (ms) and 42 value columns, with no per-channel
metadata. The reader parsed it — 42 channels, 1 group, 884 rows, 7.06 s, 125 Hz — but
`copies_collapsed` was empty: with no symbol or port there was nothing to match copies on, and
no `display_offset` to read.

The two exports at first seemed to disagree on 21 channels. They were two recordings about
three minutes apart, by their start times. Flags were raw 0/1 in both; no column was shifted.

## 3 — VS Code and Copilot: not tested

VS Code 1.134.0 was installed; the GitHub Copilot extension was not.

## 4 — `ColorMode`: answered

The options are Custom, First Channel, and each channel in the band by name. None follows the
IDE theme. The property grid showed our colours as written: canvas 37;37;38, axis text
241;241;241, grid 62;62;66. The palettes stand.

§4.9 (a parked axis) was not done. Part B is not possible on this machine.

## What was done with it

- Flags back on 0/1, with no display offset.
- The reader collapses copies in a hand export where Scope's own naming marks them — a
  `<name> (n)` beside a `<name>` with identical time and values — and `copies_collapsed` says
  `matched_on: "name"` rather than `"symbol"`. The docs say to prefer `ingest` on the `.svdx`.
- The hand-export fixture in `tests/test_verbs.py` is reconstructed from this description, not
  copied from a file.
