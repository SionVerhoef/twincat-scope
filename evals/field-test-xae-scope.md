# Field test — driving a scope through the open XAE

**Read this cold.** It assumes you have this repository, a Windows PC with TwinCAT XAE, and
nothing else: no earlier conversation, no other repository. Everything you need is here or in
the files it names.

## 1. Why you are being asked

`twincat-scope` is an agent skill for building and analysing TwinCAT 3 Scope recordings
(`SKILL.md` is the overview). Its build half, `scripts/tcscope.py newscope`, writes a
`.tcscopex` (a scope configuration) to disk and then stops. The user does the rest by hand, and
wants three of those manual steps gone:

1. **The reload popup.** When an agent changes a file that XAE has open, XAE asks whether to
   reload it. A sister skill (twincat-st, for PLC code) removed this for PLC objects by editing
   through XAE's **Automation Interface**: the COM object (`EnvDTE.DTE`) of the running XAE,
   found in the Windows Running Object Table (ROT). The user is not sure whether the popups
   they saw came from that skill's older version or from this one. **Find out whether this skill
   can cause one**: it can only do so when `newscope` overwrites a `.tcscopex` that XAE has open.
2. **"Add Existing Item".** The user adds every generated `.tcscopex` to the TwinCAT
   Measurement project (`.tcmproj`) by hand. **Find out whether the Automation Interface can do
   it** without a dialog, and how.
3. **Save and hand over the recording.** After recording, the user saves the data as `.svdx`
   to the desktop through Scope View's save dialog, then drags that file into the agent's chat.
   **Find out whether a script can save the recording to a fixed path without a dialog.** The
   agent can then read it from there, and nothing needs dragging. **Also find out whether a script can
   start and stop the recording.** The maintainer's decision: the user normally presses Record
   themselves, but the tool must be able to do it too, **only when the user explicitly asks**,
   never on its own initiative (`SKILL.md` rule 4 is to be amended to match when the tool lands). Also record where Scope View saves an `.svdx` by
   default, and whether that folder is fixed.

Nothing is known yet from a real XAE. Nobody has run the probe, or even parsed it: the
machine it was written on has no PowerShell. Your output decides what tool gets built, so
**measure and quote. Do not guess, and do not build the tool.**

## 2. What is already here

- **`scripts/probe_xae_scope.ps1`**, the probe. It is read-only by default and lists every XAE
  in the ROT, its solution's projects, each Measurement project's items with the COM type each
  item's `.Object` exposes, and every XAE command whose name contains `Scope`. `-Add <file>`
  adds one file to a Measurement project with `ProjectItems.AddFromFileCopy` (default) or
  `-Method AddFromFile`. It then reports what came back, whether a dialog opened, and the
  project's saved state. It never saves, records, builds or activates. Read it before you run it.
- How the sister skill does the same lookup: a `TcXaeShell.DTE.*` / `VisualStudio.DTE.*` entry
  in the ROT, a COM message filter so that a call XAE rejects (because a modal dialog is open)
  retries for 30 s instead of hanging, and Win32 window enumeration to read dialog text while
  COM is blocked. The probe copies that approach.
- Research leads for question 3, all unverified:
  - **Scope View .NET API.** The TE13xx Scope View manual, API chapter, describes a `ScopeProject`
    object with `StartRecord` and `SaveData`, which saves `.svdx`, in assembly family
    `TwinCAT.Measurement.Scope.API`. A `.tcscopex` names
    `TwinCAT.Measurement.Scope.API.Model` as its root element's assembly
    (`references/scope-configuration.md`).
    [InfoSys: comparison of the two Scope versions](https://infosys.beckhoff.com/content/1033/te13xx_tc3_scopeview/5975797387.html).
  - **XAE commands.** If Scope View registers its toolbar actions (Record, Stop, Save Data) as
    DTE commands, `DTE.ExecuteCommand('<name>')` drives them. The probe lists them.
  - **TF3300 Scope Server driven from the PLC** (a `FB_ScopeServerControl`-style block). It needs
    PLC code and a licence, so it is the last resort; only note whether it is installed.

## 3. Rules

- **This repository is public** (read `CLAUDE.md`). In everything you commit, call the solution
  `Scratch` and the PC "a TwinCAT 3.1.4024 engineering PC". Never commit a customer, site,
  machine or project name, an AMS NetId (use `1.2.3.4.1.1`), an IP address, a hostname or a
  user name. Redact paths to `C:\work\Scratch\…`. `py -3 scripts\check_private.py` must
  pass before every commit.
- **Scratch solution only.** Never point any of this at a solution holding a machine project.
- **Never activate, log in, download, or switch Run/Config mode.** Those are human gestures
  (`SKILL.md` rule 2). If a check needs a running target, the **user** brings it up, and only
  on a local or test runtime.
- **Recording loads the target** (`SKILL.md` rule 4). Record only on that local or test
  runtime, with the one-channel, 10 ms scope generated below, and for at most 10 s.
- **Any dialog during a check is a result.** Quote its title and text exactly. Close it the
  way a user would, and say which button you pressed.
- You may fix the **probe** if it does not parse or crashes. Commit the fix separately, saying
  what broke. Write any extra probe snippets (§5, P7) into `evals/probes/` and commit them.
  Do not write the real tool.

## 4. Setup

- Windows PowerShell 5.1 and TwinCAT XAE, both **not** elevated: an elevated XAE is invisible to
  a non-elevated shell. Python 3 as `py -3`.
- This repository at the head of branch `worktree-probe-add-scope-to-xae`. Record the commit.
- A scratch TwinCAT solution `C:\work\Scratch\Scratch.sln` with a PLC project whose `MAIN`
  declares `nCounter : UDINT;` and runs `nCounter := nCounter + 1;`, plus an empty **TwinCAT
  Measurement** project added to the solution. Commit the scratch solution to its own local git
  repository before P3, so every file change is visible with `git status` / `git diff`.
- Note whether the twincat-st skill is installed on this PC, and its version (the head of its
  `CHANGELOG.md`). Versions before 0.6.0 caused reload popups when editing PLC code, so a popup
  you see during this run has to be traced to the right skill.
- Open the solution in XAE **by hand** (Start menu → open solution), as a user would.
- Generate the test scopes, then check them:

  ```powershell
  chcp 437
  foreach ($n in 'A','B','C','D') {
    py -3 scripts\tcscope.py newscope templates\minimal-single-channel.tcscopex `
      -o "C:\work\gen\Scope$n.tcscopex" --channels "MAIN.nCounter:UDINT" `
      --sample-time-ms 10 --record-time 10
  }
  py -3 scripts\tcscope.py checkscope C:\work\gen\ScopeA.tcscopex
  # For P7, regenerate ScopeC with --netid <the test runtime's AMS NetId>: the default
  # 0.0.0.0.0.0 may not reach it. That NetId stays on the PC and never goes into the report.
  function probe { powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\probe_xae_scope.ps1 @args; "exit $LASTEXITCODE" }
  ```

## 5. Checks

Quote the full output of every probe run. Note XAE's version from P2.

| # | Do | Record | Answers |
|---|---|---|---|
| P1 | `$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("$PWD\scripts\probe_xae_scope.ps1",[ref]$null,[ref]$e); $e` | No output means it parses. Otherwise fix it, per §3 | probe usable |
| P2 | `probe` (read-only) | Every XAE, the projects with their `kind` GUIDs, the Measurement project's items, the `object=` type of each item, and the full `Scope` command list with `available=` | baseline; the command list feeds P7 |
| P2b | Only if P2 lists no project whose `file=` ends in `.tcmproj` | Find the Measurement project from P2's `kind` GUIDs and file names, fix `Test-Measurement` in the probe, commit, and re-run P2 | probe finds the project |
| P3 | `probe -Add C:\work\gen\ScopeA.tcscopex` | Did a dialog open? Is `ScopeA` in Solution Explorer? Was the file **copied** into the Measurement project's folder, or linked from `C:\work\gen`? (`git status` in Scratch.) Does XAE mark the project unsaved? Then save by hand (Ctrl+Shift+S) and quote `git diff` of the `.tcmproj` | Q2: `AddFromFileCopy` |
| P3b | Add ScopeD with the probe, then save it **through the DTE** instead of by hand: `$project.Save()` (snippet in `evals/probes/`), then separately `$dte.ExecuteCommand('File.SaveAll')` | For each call: any dialog, whether `Saved` turns True, and `git diff` of the `.tcmproj` | Q2: can a tool finish the add without a person |
| P4 | `probe -Add C:\work\gen\ScopeB.tcscopex -Method AddFromFile` | The same as P3. Does the item point at `C:\work\gen`, or was the file copied anyway? | Q2: which method matches "Add Existing Item" |
| P5 | `probe -Add C:\work\gen\ScopeA.tcscopex` again | Error, a duplicate item, a `ScopeA1`, or a dialog? | Q2: what a re-run does |
| P6 | Open `ScopeA` from the Measurement project in XAE so it is visible. Run the `newscope` line for `A` again, but write to **the path the project item uses** (P3's `file=`), with `--record-time 20`. Switch to XAE | Does XAE show a reload prompt? Quote it, answer **No**, and note what XAE shows. Repeat with the scope's document **closed** in XAE | Q1: can this skill cause the popup, and when |
| P7 | Only on the user's local/test runtime, with the user present, and with **ScopeC** added by the probe. (a) For each P2 command that looks like record/stop/save-data, run `$dte.ExecuteCommand('<name>')` with ScopeC's node selected in Solution Explorer (`$dte` from the ROT, as in the probe). (b) If P2's `object=` for ScopeC is not `__ComObject`/empty, list `$item.Object \| Get-Member` and try `StartRecord`, `StopRecord` and `SaveData('<path>.svdx')` if they exist. Save your snippet to `evals/probes/` | For each call: return or error, any dialog, did a recording start (does the chart move?), and did an `.svdx` appear (path, size)? **Most important:** after the user records and stops by hand, can a save-data call write the `.svdx` to a path you choose, with no Save dialog? Run `py -3 scripts\tcscope.py checkscope <that>.svdx`, then `ingest <that>.svdx` and `manifest` on the Parquet it names. Expect channel `nCounter` at about 100 Hz for about 10 s | Q3: record and save through XAE |
| P8 | Find the Scope View install: `Get-ChildItem C:\TwinCAT -Recurse -Filter 'TwinCAT.Measurement.Scope.API*.dll' -ErrorAction SilentlyContinue`. For each one: `[Reflection.Assembly]::LoadFrom($p).GetExportedTypes() \| ? Name -match 'ScopeProject\|Record' \| % { $_.FullName; $_.GetMethods().Name \| sort -u }` | The DLL paths (redact the root to `C:\TwinCAT\…`), the version, and the public methods of `ScopeProject` (or what stands in for it). Is TF3300 Scope Server installed (Programs and Features)? | Q3: is a standalone recorder possible without XAE |
| P9 | Close every dialog. Remove ScopeA–D from the project by hand, revert Scratch with git | Clean `git status` | clean-up |

## 6. Report

Write `evals/field-review-xae-scope.md` and open it with the commit you tested and the setup
(XAE and Windows PowerShell versions, elevated or not). Then:

- one section per check, with the command and its quoted output (redacted per §3), and pass,
  fail or "not run, because…";
- **Answers**: a short paragraph each for Q1, Q2 and Q3. Say what was measured, what the next
  tool should do, and what is still unknown. For Q3, name the path that worked (XAE command,
  item `.Object` API, standalone API, or none) and what it needs: licence, open document,
  running target;
- anything that surprised you, even off-question.

Commit the review, plus any probe fixes and `evals/probes/` snippets, to the same branch, and
push. The open pull request picks them up. Do not merge.
