# Field test — XAE verbs acceptance, and which pragmas hide a symbol from Scope

**Round 3.** Round 1 ran against `631571e` (`evals/field-review-xae-acceptance.md`), round 2
against `426d514` (`evals/field-review-xae-acceptance-2.md`). Round 2 passed everything except
`xae record`, which has changed since. **Run only:** A1, A11, R1, R3 and the new probes P1–P2
(§4, *Round 3 probes*), with the setup they need (A3, A7, A8 to have ScopeA/ScopeB in the
project and one recording). **Skip** A2, A4–A6, A9, A10, A13, R2, R4 and Part B — they passed
in round 2 and nothing they test has changed. For the skipped ones write "not run: round 2
passed".

What changed, so you know what to look at:

- `xae record` now runs the toolbar search first and checks idle state, active tab and dialogs
  right before it presses. For a named scope it no longer starts a separate `xae list` process,
  so it should press within a few seconds of starting (round 2: ~10 s).
- A `ScopeState` it does not know (round 2 saw 30) is watched like any busy state, not given up on.
- Refusals now say why when XAE is too narrow for the Scope toolbar, and what the active
  document means when a project designer tab is in front.
- `cleanup --dry-run` also lists the folders it would remove.
- P1–P2 are measurements, not pass/fail: they decide how `xae record` will protect a recording
  the scope holds but nobody saved (round 2, R3a).

**Read this cold.** It assumes you have this repository, a Windows PC with TwinCAT XAE, and
nothing else: no earlier conversation, no issue tracker, no other repository. Everything you
need is here or in the files it names.

**Your only output is one Markdown file:** `evals/field-review-xae-acceptance-3.md` (§7). Do not
commit, push or open a pull request, and do not change any code in this repository. If a check
finds a bug, describe it in the report with the exact command and output; the maintainer fixes it.

## 1. Why you are being asked

`twincat-scope` is an agent skill for building and reading TwinCAT 3 Scope recordings
(`SKILL.md` is the overview). Two things need a real XAE to settle.

**Part A — do the XAE verbs work?** `scripts/tcscope.py` gained verbs that drive the open XAE
through `scripts/xae_scope.ps1`:

- `xae list | add | save` — list the scopes in the Measurement project, add a generated
  `.tcscopex` to it and save the project, save the recording Scope View holds as an `.svdx`
- `recordings` — where `xae save` writes
- `cleanup` — deletes what `xae save` wrote

They were built on measurements from one earlier session (`evals/field-review-xae-scope.md`,
read it first), but `xae_scope.ps1` itself has **never run against a real XAE**. Only a Windows
CI job has run it, up to "no XAE found". Part A is its acceptance test.

**Part B — which pragmas keep a variable from Scope?** Scope records a PLC variable by name over
ADS. `references/scope-configuration.md` (*Pragmas that keep a symbol from Scope*) states what
Beckhoff documents and marks the rest as unknown:

- documented: `{attribute 'hide'}` and `{attribute 'tc_no_symbol'}` remove the ADS symbol;
  `{attribute 'OPC.UA.DA' := '0'}` only affects OPC UA
- unknown: what `{attribute 'symbol' := 'none'}` does in TwinCAT, and whether a pragma on a
  function block's *declaration* also hides the members of its instances
- unknown: whether a member hidden inside a block still appears as a `SubItem` of that block's
  type in the `.tmc`. If it does, `checkscope --tmc` would pass a channel Scope cannot reach

Part B measures all three. **Measure and quote. Do not guess.**

## 2. Rules

- **This repository is public** (read `CLAUDE.md`). The report will be committed by the
  maintainer, so write it as if it were public already. Call the solution `Scratch` and the PC
  "a TwinCAT 3.1 engineering PC" with its exact build number. Never write a customer, site,
  machine or project name, an AMS NetId (write `1.2.3.4.1.1`), an IP address, a hostname or a
  user name. Redact paths to `C:\work\Scratch\…`. Before you hand the report over, run
  `git add -N evals\field-review-xae-acceptance-3.md` (marks it for the checker, commits nothing),
  then `py -3 scripts\check_private.py`, which must print nothing. It only scans files git knows.
- **Scratch solution only.** Never point any of this at a solution holding a machine project.
- **Never activate, log in, download, or switch Run/Config mode yourself** (`SKILL.md` rule 2).
  Where a check needs a running PLC, the **user** activates the scratch solution on a local or
  test runtime (user-mode runtime is fine), and tells you when it runs.
- **Never press Record or start a recording yourself** (`SKILL.md` rule 4). The user records —
  except in R1 and R3, where the user asks you, in words, to run `xae record` and watches XAE
  while it runs. Never press Stop Record, never answer the *Stop Record?* popup. Keep every
  recording to the scopes generated below: 10 ms, at most 10 s.
- **Any dialog is a result.** Quote its title and text exactly, say which button you pressed.
- **Building is allowed** (Build → Build Solution): it writes the `.tmc` and touches no target.

## 3. Setup

- Windows PowerShell 5.1 and TwinCAT XAE, both **not** elevated. An elevated XAE is invisible
  to a non-elevated shell.
- Python 3.11 or newer as `py -3`. Run `py -3 scripts\tcscope.py doctor` and quote its output.
  `ingest` and `manifest` need numpy and pyarrow: use `uv run scripts\tcscope.py …` if `uv` is
  installed, else `py -3 -m pip install --user numpy pyarrow matplotlib` once. If neither is
  possible, skip those steps and say so.
- This repository at the head of `main`. Record the commit (`git rev-parse --short HEAD`).
- `chcp 437` in the shell, then define:

  ```powershell
  $sln = 'C:\work\Scratch\Scratch.sln'
  function tc { py -3 scripts\tcscope.py @args; "exit $LASTEXITCODE" }
  ```

### The scratch solution

`C:\work\Scratch\Scratch.sln` with:

1. A PLC project (port 851) on a **10 ms** task. Function blocks first:

   ```iecst
   FUNCTION_BLOCK FB_Probe
   VAR
       nValue : UDINT;
   END_VAR
   nValue := nValue + 1;
   ```

   ```iecst
   {attribute 'hide'}
   FUNCTION_BLOCK FB_ProbeHide
   VAR
       nValue : UDINT;
   END_VAR
   nValue := nValue + 1;
   ```

   `FB_ProbeNoSym` is the same with `{attribute 'tc_no_symbol'}` above `FUNCTION_BLOCK`, and
   `FB_ProbeSymNone` the same with `{attribute 'symbol' := 'none'}`. Then one with a single
   hidden member:

   ```iecst
   FUNCTION_BLOCK FB_ProbeOneHidden
   VAR
       nVisible : UDINT;
       {attribute 'hide'}
       nHidden  : UDINT;
   END_VAR
   nVisible := nVisible + 1;
   nHidden  := nHidden + 1;
   ```

   And `MAIN`:

   ```iecst
   PROGRAM MAIN
   VAR
       nCounter      : UDINT;
       nPlain        : UDINT;
       {attribute 'hide'}
       nHide         : UDINT;
       {attribute 'tc_no_symbol'}
       nTcNoSymbol   : UDINT;
       {attribute 'TcNoSymbol'}
       nTcNoSymbolCC : UDINT;
       {attribute 'symbol' := 'none'}
       nSymbolNone   : UDINT;
       {attribute 'symbol' := 'read'}
       nSymbolRead   : UDINT;
       {attribute 'OPC.UA.DA' := '0'}
       nOpcOff       : UDINT;
       fbPlain       : FB_Probe;
       fbHideType    : FB_ProbeHide;
       fbNoSymType   : FB_ProbeNoSym;
       fbSymNoneType : FB_ProbeSymNone;
       fbOneHidden   : FB_ProbeOneHidden;
   END_VAR
   nCounter := nCounter + 1;
   nPlain := nPlain + 1;          nHide := nHide + 1;
   nTcNoSymbol := nTcNoSymbol + 1; nTcNoSymbolCC := nTcNoSymbolCC + 1;
   nSymbolNone := nSymbolNone + 1; nSymbolRead := nSymbolRead + 1;
   nOpcOff := nOpcOff + 1;
   fbPlain(); fbHideType(); fbNoSymType(); fbSymNoneType(); fbOneHidden();
   ```

   If a pragma is refused by the compiler in some position, that is a result: quote the
   message, remove that one pragma, and carry on.
2. An empty **TwinCAT Measurement** project in the solution.
3. The whole `C:\work\Scratch` folder in its **own local git repository**, committed after the
   first successful build. Every check below reads `git status` / `git diff` there.

Open the solution in XAE **by hand**, as a user would. Generate the scopes **outside** the
project folder:

```powershell
mkdir C:\work\gen -Force | Out-Null
$netid = '<the test runtime''s AMS NetId>'
foreach ($n in 'A','B','C','D') {
  tc newscope templates\minimal-single-channel.tcscopex -o "C:\work\gen\Scope$n.tcscopex" `
     --channels "MAIN.nCounter:UDINT" --sample-time-ms 10 --record-time 10 --netid $netid
}
tc newscope templates\minimal-single-channel.tcscopex -o "C:\work\gen\ScopeE.tcscopex" `
   --channels "MAIN.nCounter:UDINT" --sample-time-ms 10 --record-time 60 --netid $netid
```

Pass `--netid` from the start: in round 1 the default `0.0.0.0.0.0` did not reach the runtime
even on the same PC. That NetId stays on the PC; the report says `1.2.3.4.1.1`. ScopeD is used
only in R2. ScopeE has a **60 s** window, for R3(a): long enough to still be recording when the
command starts after a chat round trip.

## 4. Part A — the XAE verbs

Quote every command with its full output. "Clean" means `git status` in `C:\work\Scratch`.

| # | Do | Pass when | Record |
|---|---|---|---|
| A1 | `$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("$PWD\scripts\xae_scope.ps1",[ref]$null,[ref]$e); $e` | no output | parse errors, if any |
| A2 | `tc xae list --solution $sln` | `ok`, no scopes | the output; XAE version if shown |
| A3 | `tc xae add C:\work\gen\ScopeA.tcscopex --solution $sln` | no dialog; `ScopeA` in Solution Explorer; `git diff` of the `.tcmproj` shows exactly one new `<Content Include="ScopeA.tcscopex">` line; the file is copied into the Measurement folder; XAE shows the project as saved (no `*`) | the diff; time taken |
| A4 | Run A3 again | refused, naming the scope the project already holds; nothing changes in git | the refusal; whether XAE still answers `xae list` afterwards |
| A5 | `tc newscope templates\minimal-single-channel.tcscopex -o <Measurement folder>\ScopeX.tcscopex --channels "MAIN.nCounter:UDINT"` | refused: Measurement project folder | the refusal |
| A6 | Open `ScopeA.tcscopex` in the Measurement folder in Notepad, add a space at the end, save, and click into XAE so its *file has been changed outside the environment* prompt appears. Leave it open and run `tc xae list --solution $sln` | refused **within a few seconds** (not after 30 s) while the dialog is open, quoting the dialog's text — not "no XAE", not an elevation hint | the refusal; then answer the prompt **Yes** (reload) and `git checkout -- .` in Scratch |
| A7 | `tc xae add C:\work\gen\ScopeB.tcscopex --solution $sln`, then `tc xae list --solution $sln`, then `tc xae save --solution $sln` (no scope named) | list shows ScopeA and ScopeB; the bare save is refused because there are two scopes | both outputs |
| A8 | **With the user, on the running runtime:** the user opens ScopeB in XAE, presses Record and lets the 10 s window stop. Then `tc xae save ScopeB --solution $sln` | no dialog; `C:\work\Scratch\Recordings\ScopeB_<yyyyMMdd-HHmmss>.svdx` exists; `git status` shows `?? Recordings/` | the output, file size |
| A9 | `tc checkscope <that .svdx>`, then `ingest` it and run `manifest` on the Parquet path `ingest` prints | about 100 Hz, about 10 s, channel `nCounter`, no gaps | the key numbers |
| A10 | `tc recordings --solution $sln --set Data\Scope`. Close XAE completely, reopen the solution by hand, have the user record ScopeB again, `tc xae save ScopeB --solution $sln`, then `tc recordings --solution $sln` | `tcscope.json` beside the `.sln` holds `Data/Scope`; the second recording lands in `C:\work\Scratch\Data\Scope\`; `recordings` names the project setting as its source | outputs; content of `tcscope.json` |
| A11 | `tc cleanup --solution $sln --dry-run`, then `tc cleanup --solution $sln --scope ScopeB`, then `tc cleanup --solution $sln` | dry run lists every recording `xae save` and `xae record` wrote, their cache files **and the folders the real run removes**, and deletes nothing; the real runs delete exactly those; the folders `xae save` created disappear once empty; XAE stays open and `xae list` still works | outputs; `git status` after (only `tcscope.json` may remain) |
| A12 | R1–R4 below | each passes | as listed there |
| A13 | Close XAE. `subst S: C:\work`. Open `S:\Scratch\Scratch.sln` in XAE by hand. `tc xae list --solution S:\Scratch\Scratch.sln`, then `xae add C:\work\gen\ScopeC.tcscopex --solution S:\Scratch\Scratch.sln`. Afterwards close XAE and `subst S: /d` | XAE is found by the `S:` path; the add works | outputs; any path written as `C:\…` where `S:\…` was expected |
| A14 | Throughout A2–A13 | no reload prompt except the one A6 provokes | every unexpected dialog, with the step it followed |

### A12 — `xae record` (R1–R4)

Use ScopeB, the scope that recorded in A8 (generated with `--netid`; the default NetId does not
connect). Before each recording, read `MAIN.nCounter` over ADS and note it.

| # | Do | Pass when | Record |
|---|---|---|---|
| R1 | Twice. **First with XAE snapped to half the screen**, then maximised. Each time the user asks you to record and clicks into the scope's tab so it is the active document. `tc xae record <scope> --solution $sln` | half width: refused, saying XAE is too narrow for the Scope toolbar, nothing pressed. Maximised: no dialog; output `ok`, `pressed` is exactly `["Start Record"]`, `states` go 60 → 50 → (70) → 60; the `.svdx` lands in the recordings folder; `ingest` + `manifest` show ~100 Hz, ~10 s, `nCounter` starting above the value read before; the user confirms nothing else happened in XAE (no restart, no mode change) | both outputs; the key numbers; the time it took, and how long after the command started the press came (first `nCounter` sample against the value read before, as in round 2) |
| R2 | The user presses Record **by hand** and, after ~3 s, Stop Record, so the *Stop Record?* popup opens. Leave it open. Run `tc xae list`, `tc xae add C:\work\gen\ScopeD.tcscopex`, `tc xae save <scope>` and `tc xae record <scope>` (each `--solution $sln`) | each refuses within a few seconds, quoting the popup's title; nothing changes in git. Then the user answers the popup | the four outputs and their times |
| R3 | Three refusals, nothing pressed: (a) add ScopeE (`tc xae add C:\work\gen\ScopeE.tcscopex`); the user opens it, presses Record by hand and asks you to record it while it runs; you run `tc xae record ScopeE` straight away; (b) with a **different** document active — the system project's tab, as in round 2; (c) on a scope with no end — in Scope View the user switches the scope to *Ringbuffer* and saves it | (a) refused, quoting `ScopeState 50` (or any value but 60), and `pressed` is empty; the user's recording runs on to its 60 s; (b) refused, explaining the active document; (c) refused, naming the ring buffer; in all three no recording starts from the command | the three outputs |
| R4 | With no dialog open, the user drags a tool window (Error List, Output) out so it **floats**. `tc xae list`. Then the user opens File → New → Project and leaves that window open. `tc xae list` again | first `ok` (a floating tool window is not a dialog); second refused, quoting the New Project window | both outputs |

### Round 3 probes — what `SaveData` does (P1–P2)

`xae record` will save whatever the scope holds before it presses Start Record, so a recording
the user made and did not save is never thrown away. Whether that is safe depends on what
`SaveData` does when the scope holds **nothing**, which has never been measured. These are
measurements: record what happens, there is no pass or fail. Run each `xae save` with the user
watching XAE, and note every dialog.

| # | Do | Record |
|---|---|---|
| P1 | Close XAE completely. Reopen the solution by hand, open ScopeB, and **do not record**. Run `tc xae save ScopeB --solution $sln` | exit code and full output; whether a `.svdx` was written and its size; if one was, `checkscope` and `ingest` + `manifest` on it (rows, duration, or the error); any dialog, its title and text, and what the user had to press; whether XAE still answers `tc xae list` afterwards |
| P2 | After a normal recording of ScopeB (the user presses Record and lets it stop), run `tc xae save ScopeB --solution $sln` **twice**, a few seconds apart | both outputs and file sizes; `ingest` both — are the samples identical (first and last `nCounter`, row count)? This says whether a held recording stays held after a save |

If P1 raises a dialog, answer it as the user sees fit, quote it exactly, and do not repeat P1.

Finish Part A by removing only what it added: `tc cleanup --solution $sln`, ScopeA–C and ScopeE
removed from the project by hand, the `.tcmproj` restored from git, `tcscope.json` deleted.
Leave anything in Scratch that Part A did not make.

## 5. Part B — which pragmas hide a symbol

**B1 — build.** Build → Build Solution. Quote every error and warning that mentions a pragma
or one of the variables above.

**B2 — what the `.tmc` holds.** The build writes `<PLC project>.tmc` beside the `.plcproj`.

```powershell
$tmc = '<path to the .tmc>'
[xml]$t = Get-Content -Raw $tmc
'--- symbols under MAIN'
$t.SelectNodes('//DataArea/Symbol') | ForEach-Object { $_.Name } | Where-Object { $_ -like 'MAIN.*' } | Sort-Object
foreach ($n in 'FB_Probe','FB_ProbeHide','FB_ProbeNoSym','FB_ProbeSymNone','FB_ProbeOneHidden') {
  "--- DataType $n"
  $dt = $t.SelectSingleNode("//DataType[Name='$n']")
  if ($dt) { $dt.SelectNodes('SubItem') | ForEach-Object { "$($_.Name)  props: $($_.Properties.OuterXml)" } } else { 'not in the .tmc' }
}
'--- full DataType FB_ProbeOneHidden'
$t.SelectSingleNode("//DataType[Name='FB_ProbeOneHidden']").OuterXml
```

Quote the output in full (every name here is a scratch name, so nothing needs redacting). Also
quote the `<Properties>` of the `MAIN.nHide` and `MAIN.fbOneHidden` symbols if they exist.

**B3 — what `checkscope --tmc` says.** Generate one scope over every probe channel and check it:

```powershell
$ch = 'MAIN.nPlain:UDINT,MAIN.nHide:UDINT,MAIN.nTcNoSymbol:UDINT,MAIN.nTcNoSymbolCC:UDINT,' +
      'MAIN.nSymbolNone:UDINT,MAIN.nSymbolRead:UDINT,MAIN.nOpcOff:UDINT,' +
      'MAIN.fbPlain.nValue:UDINT,MAIN.fbHideType.nValue:UDINT,MAIN.fbNoSymType.nValue:UDINT,' +
      'MAIN.fbSymNoneType.nValue:UDINT,MAIN.fbOneHidden.nVisible:UDINT,MAIN.fbOneHidden.nHidden:UDINT'
tc newscope templates\minimal-single-channel.tcscopex -o C:\work\gen\ScopeP.tcscopex `
   --channels $ch --sample-time-ms 10 --record-time 5
tc checkscope C:\work\gen\ScopeP.tcscopex --tmc $tmc
```

Quote the `problems` and `warnings` in full.

**B4 — what is really reachable.** With the user, on the running runtime (the user activates):

- (a) In Scope View's **Target Browser**, on the test runtime's port 851, expand `MAIN`. List
  which of the variables and block members above it shows.
- (b) `tc xae add C:\work\gen\ScopeP.tcscopex --solution $sln`; the user opens ScopeP and
  presses Record. Quote every error Scope View shows (expect *Symbolname could not be found*
  for unreachable ones). If the recording runs, `tc xae save ScopeP --solution $sln`, `ingest`
  it, and quote `manifest`'s channel list.

Then fill in this table, one row per variable:

| Variable | Pragma | Compiles? | In `.tmc` symbols / as SubItem? | `checkscope --tmc` | Target Browser shows it? | Scope records it? |
|---|---|---|---|---|---|---|
| `MAIN.nPlain` | none | | | | | |
| `MAIN.nHide` | `hide` | | | | | |
| … one row for each variable in B3's `$ch` … | | | | | | |

Finish by removing ScopeP, `cleanup --solution $sln`, and a clean `git status` in Scratch.

## 6. If something blocks you

If a step cannot run (no runtime, no user available to record, a verb crashes), write
"not run, because …" for it and carry on with the next. Part B1–B3 needs no runtime and no
user; do those even if nothing else runs.

## 7. Report

Write `evals/field-review-xae-acceptance-3.md` and nothing else. Open it with: the repository
commit you tested; TwinCAT build, Windows version, Windows PowerShell version, elevated or not;
Python version and whether `uv` was used; whether a runtime and a user were available.

Then:

- **Part A:** one section per check A1–A14 (A12 as R1–R4), then P1–P2, with the command, its quoted output (redacted per §2),
  and **pass**, **fail** or **not run, because…**. For a fail, say what you expected and what
  happened instead.
- **Part B:** round 1 only — skip it in round 3 (and answers 2–3 below).
- **Answers**, one short paragraph each:
  1. Are `xae add | save | list | record`, `recordings` and `cleanup` fit for use? Which fails block it?
  4. (Round 3) What does `SaveData` do when the scope holds nothing (P1), and does a recording
     stay held after it is saved (P2)?
  2. Which pragmas keep a symbol from Scope, including `symbol := 'none'` and a pragma on a
     block's declaration?
  3. Does a hidden member still appear as a `SubItem` in the `.tmc`? If so, quote the XML that
     tells it apart from a visible one (an attribute or property), so `checkscope --tmc` can
     learn to flag it.
- **Surprises:** anything unexpected, even off-question.

Run `git add -N evals\field-review-xae-acceptance-3.md` and `py -3 scripts\check_private.py` once
more (it must print nothing), then tell the user the report is ready at
`evals/field-review-xae-acceptance-3.md`. Do not commit it.
