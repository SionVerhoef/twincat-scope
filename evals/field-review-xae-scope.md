# Field review — driving a scope through the open XAE

One field session on an engineering PC answered which Automation Interface calls add a scope to
a TwinCAT Measurement project and save its recording without a dialog. `scripts/xae_scope.ps1`
is built on exactly these results. The probe and its raw transcripts stayed on the test PC.

## Setup

TwinCAT 3.1.4024.55, Windows 10 22H2, XAE shell `TcXaeShell.DTE.15.0`, Windows PowerShell 5.1,
not elevated. TE130x Scope View and TF3300 Scope Server 3.4.3147.18. Scratch solution: a PLC
project whose `MAIN` increments a `UDINT` counter on a 10 ms task, plus a Measurement project.
Test scope: `newscope templates\minimal-single-channel.tcscopex`, one channel `MAIN.nCounter`,
10 ms, 10 s fixed window.

## Finding the XAE and its Measurement project

- ROT entries are named `!TcXaeShell.DTE.15.0:<pid>` (`!VisualStudio.DTE.` also accepted).
- Several XAE instances can be open, one minimised with no window title, so `Get-Process` does
  not show its solution. The instance is chosen by `DTE.Solution.FullName`, and no other is read
  past that.
- An elevated XAE is invisible to a non-elevated shell, and the other way round.
- The Measurement project has no COM type information: PowerShell's adapter returns `$null` for
  every member. Late-bound `InvokeMember` works. The DTE and the PLC project are typed, and
  `InvokeMember` on the typed DTE throws `MissingMethodException` — hence adapter first, then
  late-bound. The project is recognised by `FullName -like '*.tcmproj'`.
- A message filter retrying `SERVERCALL_RETRYLATER` for 30 s was registered. No call was rejected
  in the whole session.

## Adding a scope

- `ProjectItems.AddFromFileCopy(<full path>)` on the Measurement project: no dialog, the file is
  copied into the project folder and loaded. `AddFromFile` also copies here.
- `Project.Save('')` saves the project with no dialog: `Project.Saved` goes False → True and the
  `.tcmproj` gains one `<Content Include="<name>.tcscopex">` line. `Project.Save()` with no
  argument fails late-bound with `ArgumentException: Value does not fall within the expected range.`
- `DTE.Solution.Saved` stays True throughout; only `Project.Saved` tracks the add.
- `File.SaveAll` also works but saves every dirty document, stale scopes included (below).
- Adding a name the project already holds throws `COMException 0x800706F4`, changes nothing,
  and leaves that process reading empty lists afterwards; a fresh process read fine. Hence one
  process per operation, and a name check before the add.

## The reload prompt

- Rewriting a `.tcscopex` that is a project item makes XAE ask, on its next focus, *File has
  been changed outside the environment. Reload the new file?* — with the scope's document open
  or closed. It is a standard `#32770` message box, readable with `EnumWindows`; COM calls are
  rejected while it is open.
- After answering *No*, a later `File.SaveAll` wrote XAE's in-memory scope from the **first**
  load over the new file, although `Project.Saved` was True. `checkscope` still passed on XAE's
  own serialisation (438 lines against `newscope`'s 334).
- `newscope` writing outside the project folder never caused the prompt.

## Saving the recording

- No XAE command records, stops or saves scope data: none of the 29 commands containing
  "Scope" fits, and `Scope.Export` was unavailable.
- `ProjectItem.Object` is a `ScopeProjectNode` that PowerShell's adapter cannot touch at all
  (`InvalidCastException` even on `GetType()`); `InvokeMember` by name works. Its `ScopeProject`
  property is the Scope View API object.
- **`ScopeProject.SaveData(<path>.svdx)`**, after the user recorded and the window stopped:
  143–178 ms, no dialog, a ~29.7 kB `.svdx`. Through the skill: `checkscope` ok (100 Hz, UINT32,
  10 s); `ingest` 1001 rows; `manifest` 10.0 s, 100.0 Hz, 0 gaps, 0 skew. Three times, identical.
- `StartRecord()` / `StopRecord()` return without error and record nothing. `TryCheckScopeState()`
  returns False; `CheckCommandExecuteable` predicts nothing (it reports `SaveData` False while
  `SaveData` works). A `SaveData` after the no-op `StartRecord` wrote a larger file (31.1 kB)
  with identical samples — unexplained.

## Starting a recording — a later session, same PC and scratch solution

- **Dead ends:** `ScopeProject.StartRecord()` / `StopRecord()` return without error (186 ms /
  13 ms) and record nothing. No DTE command records (every command listed, not only `Scope*`).
  `ScopeProject.GetCommands()` lists 22 Scope View menu commands; none records. Untested and no
  longer needed: `AttachClient`, `ConnectHeadlessServer`, a standalone recorder through TF3300.
- **What works: XAE's own toolbar, pressed through UI Automation.** XAE's main window holds a
  `ToolBar` named exactly `TwinCAT 3 Scope` with `Button` children `Start Record` and
  `Stop Record`, both supporting `InvokePattern`. They act on the scope whose document is
  **active** (`DTE.ActiveDocument.Name`). The same window also holds `Restart TwinCAT System`,
  `Restart TwinCAT (Config Mode)`, `Start`, `Start Display`, `Stop Display` and
  `Toggle Free Run State` — hence exact names, inside that one toolbar only.
- **`ScopeState`** (late-bound property of `ScopeProject`): 60 idle (Start enabled, Stop
  disabled), 50 recording (Start disabled, Stop enabled), 70 stopping — about 1 s, seen once at
  the end of a full window, Stop still enabled. No other value seen.
- **A full 10 s window started by script and left to stop by itself:** 60 before; 50 from +1 s to
  +9 s; 70 at +10 s; 60 at +11 s; ended after ~12.7 s. `SaveData` then wrote 29,686 bytes: 1001
  rows, `nCounter` rising by one per row from 50 above the value read over ADS just before the
  press (first sample 0.5 s after it). No dialog at any point.
- **Stopping early raises a popup that blocks XAE.** Pressing `Stop Record` at +5.6 s opened
  *Stop Record?* — "Stop Recording? Recorded dataset will still be visible.", OK / Cancel and a
  "Remember my answer" checkbox (a per-user XAE setting; never tick it). It is a WinForms window
  (`WindowsForms10.Window.8.app.0.…`) owned by XAE's main window, **not** a `#32770` box. While
  open, `ScopeState` stayed 50, late-bound calls failed or waited in the message filter, and a
  fresh process could not find the XAE. After the user pressed OK: 60, XAE normal. Saving after
  an early stop has not been tried.
- **`SaveData` and an `InvalidCastException`.** A path built with `Join-Path` is a `PSObject`
  wrapping the string; passed on as it is, COM got the wrapper and `SaveData` failed every time
  with *Specified cast is not valid*, no dialog. Cast to `[string]`, the same call wrote the file.
  The session first blamed a broken Scope View session (after `GetCommands()` or the popup) and
  restarted XAE — wrong; the wrapped path was the only cause.
- Smaller: a UI Automation `ProcessIdProperty` condition needs an `[int]`; declaring
  `IDispatch.GetIDsOfNames` from C# with `string[]` / `int[]` marshalling crashed the calling
  PowerShell (XAE survived) — `InvokeMember` by name is enough.

## Where recordings went, and deleting them

- Scope View stores no save folder of its own; its Save dialog reopens the last folder the XAE
  process saved to — on the test PC the Desktop, which held 26 `.svdx` files (~158 MB) from nine
  days, many one recording re-saved under a name with characters typed on to make it unique.
- `ingest`'s cache files were never deleted (Parquet files two weeks old).
- With the scope still open in XAE: `SaveData` into `<solution folder>\Recordings\`, `ingest`,
  then deleting the `.svdx` and both cache files all succeeded — no lock, no dialog. Without a
  `.gitignore` the folder showed as `?? Recordings/` in `git status` and vanished once emptied.

## Still unknown

- Whether removing an item through the DTE and re-adding it avoids the reload prompt.
- Saving after a recording was stopped early; `ScopeState` values other than 50 / 60 / 70; the
  toolbar and button names on a localised XAE.
- A Measurement project inside a solution folder, several Measurement projects, and other XAE
  or Scope View versions.
