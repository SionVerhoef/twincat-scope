# Field review — XAE verbs acceptance, round 3

Brief: `evals/field-test-xae-acceptance.md`, round 3: A1, A11, R1, R3 and the probes P1–P2, with
the setup A3, A7, A8. Round 2 is `evals/field-review-xae-acceptance-2.md`. Repository commit
tested: `565a329` (branch `worktree-xae-round2-fixes`, not yet on main).

## Setup

| | |
|---|---|
| TwinCAT | a TwinCAT 3.1 engineering PC, build 3.1.4024.55, XAE shell `TcXaeShell` |
| Windows | 10.0.19045 |
| Windows PowerShell | 5.1.19041.7548 (the verbs' own shell), not elevated; XAE not elevated either. Commands typed in PowerShell 7.7.0, not elevated |
| Python | 3.12.10 as `py -3`; `uv` used for `ingest` / `manifest` |
| Runtime | a test runtime, activated and started by the user (see Deviations) |
| User present | yes, for every step that needed XAE by hand, a recording or a go-ahead |

`doctor`: as in rounds 1–2 — not ok only because the analysis packages are not importable by
plain Python.

## Deviations from the brief

- Same scratch solution as rounds 1–2 (`C:\work\Scratch\…`). ScopeA–E generated in `C:\work\gen`
  with `--netid` (written `1.2.3.4.1.1`), ScopeE with `--record-time 60`.
- **Runtime switched after the first P1.** The XAE target at the start was a hardware
  controller; before any recording the user switched to a test runtime in a VM and P1 was
  repeated there. Only `xae add` and P1's empty `xae save` ran against the first target. ScopeA
  and ScopeB were removed by hand and re-added.
- §2 says "at most 10 s" per recording; R3(a)'s ScopeE has a 60 s window. R3(a) was followed.
- After R3 the designer-tab gap from round 2 was probed read-only, plus two extra `xae record`
  runs the user asked for (*Extra checks*).
- At the end only Part A's own leftovers were removed.

## Part A

`tc` = `py -3 scripts\tcscope.py`, `$sln` = `C:\work\Scratch\Scratch.sln`. Times are wall clock
for the whole call.

| Step | Result | Notes |
|---|---|---|
| A1 parse | pass | no parse errors under 5.1 and 7.7.0 |
| A3 `xae add ScopeA` (setup) | pass | 2173 ms; again 1019 ms after the runtime switch; one relative `<Content Include>`; no dialog, no `*` |
| A7 ScopeB, list, bare save (setup) | pass | add 1221 / 896 ms, list 718 ms, bare save refused "holds 2 scopes" 670 ms |
| A8 `xae save ScopeB` (setup) | pass | 29,686 B, 1363 ms, no dialog (also P2's first save) |
| A11 cleanup | pass | dry run lists the three recordings, six cache files and the `Recordings` folder, deletes nothing; `--scope ScopeB` deleted exactly that list; bare cleanup afterwards `deleted: []`; XAE stayed open |
| R1 half width | pass | refused in 2287 ms: "XAE's window is too narrow, so the toolbar moved its buttons into its overflow (>>) - toolbar shows: Toolbar Options", with the widen/maximise fix; nothing pressed |
| R1 maximised | pass | ok in 13,757 ms (round 2: 22.7 s); states 60 → 50 (0.6 s) → 60 (10.6 s); 31,096 B; 1001 rows, 100 Hz, 0 gaps; press ~2 s after the command started (round 2: ~10 s) |
| R3(a) user recording ScopeE (60 s) | pass | refused in 2454 ms "ScopeE.tcscopex is not idle: ScopeState 50 (recording)"; no `pressed` field (refused before the press step); the user's recording ran on to 60 s |
| R3(b) system project tab in front | pass | refused in 2193 ms; it named `ScopeE.tcscopex`, the last scope document |
| R3(c) ring buffer | pass | refused in Python in 363 ms |
| A14 dialogs | pass | no verb raised a dialog |
| Others | not run: round 2 passed | A2, A4–A6, A9, A10, A13, R2, R4 |

**Extra: `xae add` over unsaved project changes — pass.** After the user removed ScopeA and ScopeB
by hand without saving, both re-adds were refused "the Measurement project … has unsaved changes"
(820–1206 ms). After the user saved, the two adds wrote exactly the two relative lines back.

## P1 — `xae save` on a scope that holds nothing

XAE closed, reopened by hand, ScopeB opened, not recorded. Run on both targets, same result:

```json
{
  "ok": false,
  "error": "SaveData failed: ApplicationException: Invalid ScopeState! Reply requested, actual: Config",
  "fix": "Is there a recording held in Scope View for this scope? Press Record, let it stop, then save."
}
```

Exit 1, 816 / 924 ms. No `.svdx`, no `Recordings\` folder, no dialog; `xae list` answered ok
straight afterwards.

## P2 — two saves after one recording

| | save 1 | save 2 (5 s later) |
|---|---|---|
| time | 1363 ms | 1270 ms |
| size | 29,686 B | 29,686 B |
| rows / duration / rate / gaps / skew | 1001 / 10.0 s / 100 Hz / 0 / 0 ms | the same |
| `nCounter` first → last | +1 per row, 1000 apart | the same values |
| SHA-256 of time + `nCounter` columns | `b900fbac088e0ed8…` | `b900fbac088e0ed8…` |
| SHA-256 of the `.svdx` | — | differs from save 1 |

Identical samples, different file bytes at the same size. A held recording stays held after a save.

## Extra checks — the designer-tab gap, and ScopeState 20

**The gap.** With a designer in front, `DTE.ActiveDocument` names the last scope document clicked;
if that is the scope asked for, the active-document check passes. Read-only probe:

| | ScopeB tab in front | system project tab in front |
|---|---|---|
| `DTE.ActiveDocument.Name` | ScopeB.tcscopex | ScopeB.tcscopex |
| Scope toolbar Start Record | enabled | **disabled** |
| Stop Record / Save Data / Create Report | disabled | disabled |
| UI Automation selected document tab | ScopeB | Scratch (system project) |

XAE enables the Scope toolbar only while a scope's tab is in front, and record checks `IsEnabled`
right before pressing, so the gap cannot lead to a press. Its refusal there would read
"'Start Record' is not enabled in XAE" with the fix "Is a recording already running, or the
runtime stopped?" — wrong for this case.

**ScopeState 20 is Config.** `ScopeState` of every scope read 20 — ScopeA had never recorded —
while the runtime ran. With ScopeE in front: still 20; Start Record enabled, Stop Record and Save
Data disabled; no recording loaded. `xae save ScopeE` gave P1's error ("actual: Config"). ScopeE's
60 s recording from R3(a), which R3(b) had still seen at 60, was no longer held; what moved every
scope to Config is not known — the user saving ScopeB with the ring-buffer change (R3c) is the
only change in between.

On the user's request, with ScopeE in front and Start Record enabled:

```json
{ "ok": false, "error": "ScopeE.tcscopex is not idle: ScopeState 20 (a state this tool does not know)",
  "fix": "Wait until Scope View has stopped, save any recording it holds, then run again." }
```

Exit 1, 2092 ms, nothing pressed. **`xae record` refuses whenever Scope View holds no recording**
— the state after XAE opens — so it cannot make a session's first recording. Every successful
`xae record` so far ran on a scope recorded by hand earlier in the same XAE session.

## Answers

1. `add`, `list`, `save`, `recordings` and `cleanup` are fit for use. `record` improved where
   round 2 failed: a clear "too narrow" refusal, the press ~2 s after the command (was ~10 s), a
   user's running recording never pressed over, and a designer tab in front cannot lead to a
   press. **One fail blocks release of `record`:** it refuses ScopeState 20, so it cannot make a
   session's first recording, and its fix text sends the user after a recording that is not
   running. Minor: the `IsEnabled` refusal's fix text does not cover a designer in front.
4. With nothing held, `SaveData` throws "Invalid ScopeState! Reply requested, actual: Config"
   within a second, writes nothing and raises no dialog — a save-before-press step is safe. A held
   recording stays held after a save. But a held recording can also disappear without anyone
   saving it, as ScopeE's did.

## Surprises

- ScopeState 20 = Config, for every scope at once, with nothing recorded and the runtime running.
  Known values: 20 (Config, nothing held), 30 (seen 0.7 s after a press), 50 (recording),
  60 (holds a recording), 70 (stopping).
- A held recording was lost without a save or a new recording; suspect: saving another scope's
  configuration. Not proven.
- `ActiveDocument` lags the front tab even when the last document is a scope.
- Two saves of one recording: identical samples, different `.svdx` bytes, same size.
- Timings back near round 1: list 0.7–0.9 s, add 0.9–2.2 s, save 1.3–1.4 s.
- The brief's §2 limit "at most 10 s" contradicts R3(a)'s 60 s ScopeE.
