# Field review — XAE verbs acceptance, round 4

Brief: `evals/field-test-xae-acceptance.md`, round 4: A1, A11, R1, R3 and probe P3, with the
setup A3, A7. Round 3 is `evals/field-review-xae-acceptance-3.md`. Repository commit tested:
`4a9afab` (branch `worktree-xae-round2-fixes`, not yet on main).

## Setup

| | |
|---|---|
| TwinCAT | a TwinCAT 3.1 engineering PC, build 3.1.4024.55, XAE shell `TcXaeShell` |
| Windows | 10.0.19045 |
| Windows PowerShell | 5.1.19041.7548 (the verbs' own shell), not elevated; XAE not elevated either. Commands typed in PowerShell 7.7.0, not elevated |
| Python | 3.12.10 as `py -3`; `uv` used for `ingest` / `manifest` |
| Runtime | the test runtime in a VM from round 3, activated and started by the user |
| User present | yes, for every step that needed XAE by hand, a recording or a go-ahead |

## Deviations from the brief

- Same scratch solution as rounds 1–3. ScopeA, B and E reused from round 3 (`--netid`, written
  `1.2.3.4.1.1`; ScopeE 60 s).
- R1(a): the `nCounter` read before the command failed — the tester's ADS helper ran in
  PowerShell 7, where `TwinCAT.Ads.dll` cannot load `TcAdsDll.dll`. A read 22 s later in Windows
  PowerShell 5.1 is used instead; every later read used 5.1.
- P3: the user saved ScopeB with Save All rather than saving ScopeB alone; ScopeB's file on disk
  did change.
- At the end only Part A's own leftovers were removed.

## Part A

| Step | Result | Notes |
|---|---|---|
| A1 | pass | no parse errors |
| A3 | pass | 1974 ms, no dialog, one `<Content Include="ScopeA.tcscopex">` |
| A7 | pass | add 1082 ms; list shows A and B (873 ms); bare save refused (1117 ms) |
| A11 | **fail (minor)** | files right; an empty `Recordings` folder left behind and forgotten |
| R1 (a)–(d) | pass | all as the brief expects |
| R3 (a)–(c) | pass | refused, nothing pressed |
| A14 | pass | no dialog in any step |
| P3 | measured | held recording not dropped |
| Others | not run: passed in round 2 or 3 | |

### R1 — four records of ScopeB

"Press after" = first sample's `nCounter` minus the value read just before the command, at 10 ms
a cycle.

| | Result | Recording(s) | Press after |
|---|---|---|---|
| (a) fresh XAE | ok, 14.1 s, states 20 → 50 (0.6 s) → 60 (10.7 s), `pressed: ["Start Record"]`, no `held_saved` | 1001 rows, 100 Hz, 10.0 s, 0 gaps | ~2.5 s (from the later read) |
| (b) half width | refused in 2235 ms, too narrow, nothing pressed — **but `held_saved` written** | held copy = (a)'s samples | — |
| (c) maximised | ok, 13.3 s, states 60 → 50 (0.5 s) → 60 (10.2 s), `held_saved` | held = (a)'s samples; new 1001 rows, 100 Hz, 0 gaps | ~3.2 s |
| (d) after the user's own | ok, 14.3 s, states 60 → 50 (0.5 s) → 60 (11.2 s), `held_saved` | held = the user's recording (its `nCounter` range lies between the reads before the user's press and before the command); new 1001 rows | ~2.8 s |

The round-3 blocker passes: a session's first recording starts from ScopeState 20. Every R1
`.svdx` is 29,686 bytes.

### R3 — three refusals

- **(a)** User recording ScopeE: "ScopeE.tcscopex is busy: ScopeState 50 (recording)", 2302 ms;
  no `pressed`, no `held_saved`, no file. The user's recording ran on to 60 s.
- **(b)** ScopeB's tab clicked, then the system project's tab; probe: `ActiveDocument` ScopeB,
  Start Record (and the whole Scope toolbar) disabled. Refused "'Start Record' is disabled in XAE"
  with the new fix naming the tab in front, 2582 ms — **again with a `held_saved` copy written**.
- **(c)** Ring buffer: refused in Python, 338 ms, before XAE is touched.

### P3 — does saving one scope's configuration drop another's recording?

ScopeE's 60 s recording from R3(a) stopped by itself; the user changed a channel colour in ScopeB
and pressed Save All. `xae save ScopeE`: ok, 80,338 bytes, 1085 ms, 6001 rows, 100 Hz, 60.0 s,
0 gaps — the user's recording. **Not dropped**; this does not explain round 3's lost recording.

### A11 — cleanup, run last

The dry run listed the 8 `.svdx` (ScopeB ×3, ScopeB `_before-record` ×4, ScopeE ×1), their cache
files and the `Recordings` folder. `--scope ScopeB` deleted the 7 ScopeB files and their cache
files, no folder; the full cleanup then deleted ScopeE's file, no folder. `Recordings` remained,
empty, with the ledger at `{"files": []}`, so no later cleanup removes it.

Cause: only the ledger entries of the save that created the folder carry it in `created_dirs`.
`cleanup --scope ScopeB` dropped those entries while ScopeE's file still kept the folder
non-empty; ScopeE's entry had no `created_dirs`. The dry run counted both runs' files as gone at
once, which is why it listed the folder.

## Answers

1. All verbs fit for use; one minor cleanup gap (above). Nothing blocks.
4. `xae record` is fit for release: it makes a session's first recording, saves a held recording
   before pressing (the user's own included), refuses a running recording, a designer in front, a
   narrow window and a ring buffer with the right reason, and presses ~2.5–3.2 s after the
   command starts. To tidy: a refusal after the held-save still writes a `_before-record` copy.
   P3: no — saving another scope's configuration did not drop the held recording.

## Surprises

- **A refused record still writes a `_before-record` file.** The held recording was saved before
  the toolbar, active-document and enabled checks, so R1(b) and R3(b) each left a copy; every
  retry adds one. Four of this round's eight files were such copies.
- With the system project in front, XAE disables the whole Scope toolbar while `ActiveDocument`
  still names the scope.
- `.svdx` sizes are fixed by window at one UDINT channel: 29,686 bytes for 10 s, 80,338 for 60 s.
