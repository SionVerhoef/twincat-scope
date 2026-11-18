# Field review — XAE verbs acceptance, round 2

Brief: `evals/field-test-xae-acceptance.md`, round 2: Part A only (A1–A14, A12 as R1–R4), Part B
skipped. Round 1 is `evals/field-review-xae-acceptance.md`. Repository commit tested: `426d514`
(main).

## Setup

| | |
|---|---|
| TwinCAT | a TwinCAT 3.1 engineering PC, build 3.1.4024.55, XAE shell `TcXaeShell` |
| Windows | 10.0.19045 |
| Windows PowerShell | 5.1.19041.7548 (the verbs' own shell), not elevated; XAE not elevated either. Commands were typed in PowerShell 7.7.0, also not elevated |
| Python | 3.12.10 as `py -3`; `uv` installed and used for `ingest` / `manifest` |
| Runtime | TwinCAT RT (x64) on the same PC, activated and started by the user |
| User present | yes, for every step that needed XAE by hand, a recording or a go-ahead |

`doctor`: identical to round 1 — exit 1 only because numpy, pyarrow and matplotlib are not
importable by plain Python; python, uv, `TC3ScopeExportTool.exe` and the cache directory ok.

## Deviations from the brief

- The scratch solution is the one round 1 used (a PLC project with a small test suite besides
  `MAIN`, port 851, 10 ms task, an empty Measurement project), written `C:\work\Scratch\…` here.
  Part A only needs `MAIN.nCounter`, so the Part B probe code was not added. ScopeA–D were
  generated in `C:\work\gen` with `--netid` (the runtime's NetId, written `1.2.3.4.1.1`).
- No commits in the scratch repository. `git status` was saved as a baseline and every
  `git status` below is read against it.
- **A6 restore.** `ScopeA.tcscopex` is untracked in the scratch repository, so it was restored by
  copying `C:\work\gen\ScopeA.tcscopex` back; SHA-256 identical afterwards.
- **A6 trigger.** The space was appended by `Add-Content -NoNewline` rather than in Notepad. A
  watcher polled XAE's top-level windows every 200 ms and ran `xae list` the moment the `#32770`
  box appeared, as in round 1.
- **R1 was run twice.** The first attempt failed with XAE snapped to half the screen; the user
  maximised XAE and asked again.
- The user restarted XAE once between R3 and R4 and made unrelated changes to the system project
  for a separate test; this is why the XAE process id changes between R2 and R4.
- At Part A's end only Part A's own leftovers were removed (with XAE closed): `cleanup`, the
  `.tcmproj` restored from git, ScopeA–C, `tcscope.json`, `VSSettings/`.

## Part A — the XAE verbs

`tc` = `py -3 scripts\tcscope.py`, `$sln` = `C:\work\Scratch\Scratch.sln`. Times are wall clock
for the whole `tc` call, from a fresh process.

| Step | Result | Notes |
|---|---|---|
| A1 parse | pass | no parse errors under 5.1 and 7.7.0 |
| A2 `xae list` | pass | exit 0, 2637 ms, `scopes: []` |
| A3 `xae add ScopeA` | pass | exit 0, 4334 ms; `.tcmproj` gained one relative `<Content Include>`; copy byte-identical; no `*`, no dialog |
| A4 add again | pass | refused "already holds ScopeA.tcscopex", exit 1, 1835 ms; `list` afterwards ok |
| A5 `newscope` into the Measurement folder | pass | refused, exit 1, 270 ms, nothing written |
| A6 `list` with the reload prompt open | **pass** (round 1: fail) | refused in 2.8 s (round 1: ~31 s) quoting the dialog, no elevation hint |
| A7 ScopeB, list, bare save | pass | bare `save` refused "holds 2 scopes; say which", listing both |
| A8 `xae save` after a recording | pass | 29,691 bytes, exit 0, 2657 ms, no dialog |
| A9 `.svdx` round trip | pass | 1001 rows, 100 Hz, 0 gaps, 0 ms skew; `nCounter` +1 per row |
| A10 project recordings setting across an XAE restart | pass | `Data/Scope` stored relative; save after restart went there |
| A11 `cleanup` | **pass** (round 1 minor fail fixed) | real run removed both `.svdx`, four cache files and `Data\Scope`, `Recordings`, `Data` |
| A12 R1 record on request | **fail** at half screen width, pass maximised | see below |
| A12 R2 every verb while *Stop Record?* is open | pass | all four refused in 1.2–1.4 s quoting the WinForms popup |
| A12 R3 refusals | (a) **fail**, (b) pass, (c) pass | see below |
| A12 R4 floating tool window, then New Project | pass | floating window ignored; WPF *New Project* now caught (728 ms) |
| A13 solution through a `subst` drive | pass | every path came back as `S:\…`; `.tcmproj` holds only relative paths |
| A14 dialogs throughout | pass | no verb raised a dialog |

A11 minor: the dry run listed only files; the real run also listed the three folders it removed.

### R1 — record on request

**At half width (window 960 px):**

```json
{ "ok": false, "error": "expected exactly one 'Start Record' button in the TwinCAT 3 Scope toolbar, found 0" }
```

Exit 1, 11191 ms, nothing pressed. Read through UI Automation: the *TwinCAT 3 Scope* toolbar was
squeezed to 23 px at the end of its row and its only child was `Button 'Toolbar Options'` —
Start Record, Stop Record and Save Data had moved into the overflow (») and are not children of
the toolbar there. The refusal gave no fix and did not say why.

**Maximised:** `ok`, `pressed: ["Start Record"]`, states 60 → 50 (0.5 s) → 70 (10.5 s) → 60
(11.1 s), `recorded_s` 11.2, 31,096 bytes, exit 0 in 22,666 ms. Ingest: 1001 rows, 10.0 s,
100 Hz, 0 gaps; `nCounter` +1 per row. The first sample is 1020 counts (10.2 s) after a value read
0.08 s before the command started, so the press came roughly 9–10 s after the command started.

### R3 — refusals

**(a) The user presses Record by hand, then `xae record` runs straight away.**

```json
{
  "ok": false,
  "error": "ScopeState 30 after Start Record, a value this tool does not know; not touching the scope",
  "pressed": [ "Start Record" ],
  "states": [ { "s": 0, "state": 60 }, { "s": 0.7, "state": 30 } ]
}
```

Exit 1, 12,399 ms. Expected: refused quoting ScopeState 50, nothing pressed. Happened: the state
read before pressing was already 60 — the user's 10 s recording had ended during the chat round
trip plus the command's ~10 s start-up — so Start Record was pressed and a second recording
started. On the unknown ScopeState 30 the tool gave up and left that recording running; it ran its
full 10 s, stopped by itself, and was not saved. A read-only UI Automation search for the same
toolbar took 1.7–2.5 s, so the state the press acted on was ~2 s older than the check.

**(b) A different document active.** Refused, nothing pressed: "Start Record acts on the active
document, which is 'FB_AddMethod.TcPOU', not ScopeB.tcscopex". The user had clicked the system
project's tab — a designer, not a document — so `DTE.ActiveDocument` named the last text
document. Correct refusal; misleading name.

**(c) A scope with no end** (`<StopMode>ClientStop</StopMode>`). Refused, nothing pressed, exit 1,
6028 ms.

## Answers

`add`, `list`, `save`, `recordings` and `cleanup` are fit for use. Round 1's A6 fail is fixed:
with any dialog open every verb refuses in about 1–3 s, quoting it, and touches nothing. `record`
works on the intended path and its refusals R2, R3(b), R3(c), R4 hold. Two findings block relying
on it unattended: R3(a) — it pressed Start Record on a scope the user had just recorded with,
because ~10 s of start-up let that recording finish before the idle check, then gave up on the
unknown ScopeState 30 and left its own recording unsaved; and R1 — a too-narrow XAE makes it
fail with a message that does not say why. Neither changed the target or XAE's mode.

## Surprises

- The Scope toolbar overflows on a half-width XAE; UI Automation then shows only *Toolbar Options*.
- ScopeState 30 exists; it turned up 0.7 s after a press.
- `xae record` needs ~10 s before it presses: two XAE look-ups in two PowerShell processes, plus
  the UI Automation search.
- `ActiveDocument` is not the active tab when a project designer is in front.
- Recording sizes vary: 29,691, 29,686 and 31,096 bytes for three 1001-row, one-channel
  recordings; the larger came from `xae record`, as in round 1.
- Timings slower than round 1: `list` 0.7–2.9 s, `add` 2.4–4.3 s, `save` 2.7–4.7 s, against
  0.7 / 0.9–1.0 / 1.2 s. Possibly a test suite running in the PLC; not measured.
- `checkscope` prints the channel's AMS NetId; anyone pasting its output into a report has to
  redact it.
