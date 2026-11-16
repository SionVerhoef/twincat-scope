# Field review — XAE verbs acceptance, and which pragmas hide a symbol from Scope

Brief: `evals/field-test-xae-acceptance.md`. Repository commit tested: `631571e` (main).

## Setup

| | |
|---|---|
| TwinCAT | a TwinCAT 3.1 engineering PC, build 3.1.4024.55, XAE shell `TcXaeShell.DTE.15.0` |
| Windows | 10.0.19045 |
| Windows PowerShell | 5.1.19041.7548, not elevated; XAE not elevated either |
| Python | 3.12.10 as `py -3`; `uv` installed and used for `ingest` / `manifest` |
| Runtime | TwinCAT RT (x64) on the same PC, activated and started by the user |
| User present | yes, for every step that needed XAE by hand or a recording |

`doctor` (exit 1 only because the analysis packages are not installed for plain Python):

```json
{ "ok": false, "checks": [
  { "check": "python", "ok": true, "detail": "Python 3.12.10" },
  { "check": "uv", "ok": true, "detail": "...\\uv.EXE" },
  { "check": "numpy", "ok": false, "detail": "not importable", "fix": "uv run tcscope.py ... installs it automatically" },
  { "check": "pyarrow", "ok": false, "detail": "not importable", "fix": "uv run tcscope.py ... installs it automatically" },
  { "check": "matplotlib", "ok": false, "detail": "not importable", "fix": "uv run tcscope.py ... installs it automatically" },
  { "check": "TC3ScopeExportTool.exe", "ok": true, "detail": "C:\\TwinCAT\\Functions\\TF3300-Scope-Server\\TC3ScopeExportTool.exe" },
  { "check": "cache directory", "ok": true, "detail": "%LOCALAPPDATA%\\tcscope\\cache" } ] }
```

## Deviations from the brief

- The scratch solution was an existing TwinCAT scratch solution, not one created at
  `C:\work\Scratch`. It is called Scratch here and all paths are written as `C:\work\Scratch\…`
  and `C:\work\gen\…`. Its PLC project already held a small test suite besides `MAIN`; the probe
  code of §3 was added to it unchanged. One PLC project, port 851, 10 ms task (`MAIN.nCounter`
  advanced 993 → 1041 in 0.5 s over ADS).
- **ScopeB2 instead of ScopeB for recordings (A8–A11).** ScopeA–C were generated with the default
  NetId. Recording ScopeB failed in Scope View with *Error on connect channel: 'nCounter
  (MAIN.nCounter)' Target not connected: '0.0.0.0.0.0 Port: 851'*. As §3 allows, the scope was
  regenerated with the runtime's NetId (`1.2.3.4.1.1` here). Because ScopeB was already a project
  item, the new file was called ScopeB2 and added with `xae add`.
- The scratch repository was committed between steps so each step's `git diff` stood alone; Part
  A's end state is kept on a branch there. At the end of Part A the scopes were removed by
  `git reset --hard` to the empty-project commit with XAE closed, not by hand — this raises no
  reload prompt.
- A6's restore was limited to `ScopeA.tcscopex`: `git checkout -- .` would also have reverted
  ScopeB's line in the `.tcmproj` while XAE held it (A6 was repeated after A7).
- A6 was run three times. The first run raced the user answering the prompt and is discarded. The
  other two used a watcher that polled XAE's top-level windows every 200 ms and ran `xae list` the
  moment the `#32770` box appeared, then checked it was still open afterwards.
- B4 added ScopeP2 (the nine channels `checkscope --tmc` resolved), because Scope View refused
  ScopeP at its first unknown symbol and so recorded nothing.

## Part A — the XAE verbs

Throughout: `tc` = `py -3 scripts\tcscope.py`, `$sln` = `C:\work\Scratch\Scratch.sln`.

### A1 — parse — pass

```
PS 5.1> $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("$PWD\scripts\xae_scope.ps1",[ref]$null,[ref]$e); $e
(no output; $e.Count = 0)
```

### A2 — `xae list` — pass

```json
{ "ok": true, "solution": "C:\\work\\Scratch\\Scratch.sln",
  "project": "TwinCAT Measurement Project1",
  "project_path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\TwinCAT Measurement Project1.tcmproj",
  "scopes": [] }
```

Exit 0. No XAE version in the output. A second XAE holding another, unrelated solution was open
during most of Part A; no verb ever listed or touched it.

### A3 — `xae add ScopeA` — pass

```json
{ "ok": true, "item": "ScopeA.tcscopex",
  "path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\ScopeA.tcscopex",
  "project": "TwinCAT Measurement Project1", "project_saved": true }
```

Exit 0, took 1016 ms.

```diff
   </PropertyGroup>
+  <ItemGroup>
+    <Content Include="ScopeA.tcscopex">
+      <SubType>Content</SubType>
+    </Content>
+  </ItemGroup>
 </Project>
```

The copy in the Measurement folder is byte-identical to `C:\work\gen\ScopeA.tcscopex` (same
SHA-256). No dialog appeared. `git status`: the `.tcmproj` modified, `ScopeA.tcscopex` untracked.

### A4 — add ScopeA again — pass

```json
{ "ok": false, "error": "the Measurement project already holds ScopeA.tcscopex",
  "fix": "Generate it under a new name with newscope -o, then add that." }
```

Exit 1. `git status` clean afterwards; `xae list` straight after answered ok with ScopeA.

### A5 — `newscope` into the Measurement folder — pass

```json
{ "ok": false,
  "error": "C:\\work\\Scratch\\TwinCAT Measurement Project1 is a TwinCAT Measurement project folder; XAE watches the files in it, and rewriting one it holds can lose the new version",
  "fix": "Write the .tcscopex outside the project folder, then add it with: tcscope.py xae add <file> --solution <.sln>" }
```

Exit 1. No `ScopeX.tcscopex` was written.

### A6 — `xae list` while the reload prompt is open — **fail** (reproduced twice)

The prompt, read through Win32 while open (both runs identical):

```
'TcXaeShell' | &Yes | &No | Cancel |
C:\work\Scratch\TwinCAT Measurement Project1\ScopeA.tcscopex  File has been changed outside the environment. Reload the new file?
```

Run 2 (run 3 the same, to the second):

```
07:44:18.750 dialog seen: 'TcXaeShell' | &Yes | &No | Cancel | C:\work\Scratch\TwinCAT Measurement Project1\ScopeA.tcscopex  File has been changed outside the environment. Reload the new file?
{ "ok": false,
  "error": "no XAE has C:\\work\\Scratch\\Scratch.sln open (2 XAE/Visual Studio instance(s) checked)",
  "fix": "Open the solution in TwinCAT XAE. An XAE running as administrator is invisible to a shell that is not, and the other way round: run both at the same level." }
exit 1
07:44:49.795 dialog after list: (the same prompt, still open)
```

Expected: refused, quoting the dialog. Happened: after ~31 s, a wrong diagnosis ("no XAE"), with
a wrong fix (elevation). Nothing was changed and XAE was unharmed.

Likely cause (from reading `scripts/xae_scope.ps1`, not measured): `Find-Xae` reads
`$r.Obj.Solution.FullName` over COM before `Assert-NoDialog` runs. While the prompt is open XAE
rejects the call, the message filter retries for its 30 s, the catch swallows the failure, and the
instance looks like it has no solution. The pid is already in the ROT name
(`!TcXaeShell.DTE.15.0:<pid>`), so the `#32770` check could run before any COM call; and a
rejected call after the retry window could be reported as "XAE is busy or shows a dialog".

After the user pressed Yes, `git checkout` of `ScopeA.tcscopex` raised the same prompt once more
on the next focus (expected); after Yes, `xae list` answered normally.

### A7 — ScopeB, list, bare save — pass

```json
{ "ok": true, "item": "ScopeB.tcscopex", "path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\ScopeB.tcscopex",
  "project": "TwinCAT Measurement Project1", "project_saved": true }
```
(took 912 ms)
```json
{ "ok": true, "solution": "C:\\work\\Scratch\\Scratch.sln", "project": "TwinCAT Measurement Project1",
  "project_path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\TwinCAT Measurement Project1.tcmproj",
  "scopes": [ { "name": "ScopeA.tcscopex", "path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\ScopeA.tcscopex" },
              { "name": "ScopeB.tcscopex", "path": "C:\\work\\Scratch\\TwinCAT Measurement Project1\\ScopeB.tcscopex" } ] }
{ "ok": false, "error": "the Measurement project holds 2 scopes; say which to save",
  "fix": "tcscope.py xae save <scope> --solution <.sln>   (scopes: ScopeA.tcscopex, ScopeB.tcscopex)" }
```

Exit 1 on the bare save. The `.tcmproj` gained one `<Content Include="ScopeB.tcscopex">`,
alphabetically after ScopeA.

### A8 — `xae save` after a recording — pass (on ScopeB2, see Deviations)

The user opened ScopeB2, pressed Record, the 10 s window stopped by itself.

```json
{ "ok": true,
  "output": "C:\\work\\Scratch\\Recordings\\ScopeB2_20261116-075323.svdx",
  "bytes": 29692, "scope": "ScopeB2.tcscopex",
  "recordings_dir": "C:\\work\\Scratch\\Recordings", "recordings_dir_source": "default",
  "next": "tcscope.py ingest C:\\work\\Scratch\\Recordings\\ScopeB2_20261116-075323.svdx",
  "note": "Kept, across sessions, until the user says they are finished with this problem and `tcscope.py cleanup` runs - it can be reopened in Scope View or analysed again until then." }
```

Exit 0, took 1192 ms. No dialog. `git status` showed `?? Recordings/` (besides the build and
activation output the user had just produced).

### A9 — the `.svdx` round trip — pass

- `checkscope`: ok, one channel `MAIN.nCounter`, UINT32, 100.0 Hz, port 851, fixed 10 s window,
  `problems: []`; one warning (fixed window, no trigger) — as designed.
- `ingest` (through `uv run`): 1001 rows, columns `g0.time`, `g0.nCounter`.
- `manifest`: duration 10.0 s, median interval 0.01 s, 100.0 Hz, 0 gaps, max skew 0.0 ms, declared
  and measured sample time 10 ms, `nCounter` not constant, no NaN.
- `nCounter` 14460 → 15460 over the 1001 rows.

### A10 — project recordings setting across an XAE restart — pass

`tc recordings --solution $sln --set Data\Scope`

```json
{ "ok": true, "recordings_dir": "C:\\work\\Scratch\\Data\\Scope",
  "source": "project setting C:\\work\\Scratch\\tcscope.json", "written": "C:\\work\\Scratch\\tcscope.json" }
```

`tcscope.json`:

```json
{
  "recordings_dir": "Data/Scope"
}
```

XAE closed (it asked to save ScopeB2 — see Surprises), reopened by hand, the user recorded again:

```json
{ "ok": true, "output": "C:\\work\\Scratch\\Data\\Scope\\ScopeB2_20261116-075631.svdx", "bytes": 31102,
  "scope": "ScopeB2.tcscopex",
  "recordings_dir": "C:\\work\\Scratch\\Data\\Scope",
  "recordings_dir_source": "project setting C:\\work\\Scratch\\tcscope.json",
  "next": "tcscope.py ingest C:\\work\\Scratch\\Data\\Scope\\ScopeB2_20261116-075631.svdx",
  "note": "Kept, across sessions, until the user says they are finished with this problem and `tcscope.py cleanup` runs - it can be reopened in Scope View or analysed again until then." }
```

`tc recordings --solution $sln`

```json
{ "ok": true, "recordings_dir": "C:\\work\\Scratch\\Data\\Scope", "source": "project setting C:\\work\\Scratch\\tcscope.json" }
```

The second recording is new: 1001 rows, `nCounter` 32840 → 33840.

### A11 — cleanup — pass, with one minor fail

- Dry run: listed both `.svdx` and their four cache files (`<stem>-<hash>.csv` / `.parquet` in
  `%LOCALAPPDATA%\tcscope\cache`), `kept: []`; all six files still present afterwards.
- Extra check: `--scope ScopeB --dry-run` → `deleted: []`. The name ScopeB is a prefix of the
  recordings' `ScopeB2_…`; the tool did not match them.
- `--scope ScopeB2` deleted exactly the six files, then `C:\work\Scratch\Recordings` and
  `C:\work\Scratch\Data\Scope`. The bare cleanup after it: `deleted: []`. XAE stayed open and
  `xae list` answered ok.

**Minor fail:** the empty parent `C:\work\Scratch\Data` was left behind. `xae save` created both
`Data` and `Data\Scope`; cleanup removed only `Data\Scope`. Git shows no empty folders, so the
leftover is visible only in Explorer. `git status` afterwards, beyond the scopes still in the
project at that point: only `tcscope.json`.

### A12 — `xae record` — pass

```json
{ "ok": false,
  "error": "starting or stopping a recording from a script does not work yet: StartRecord and StopRecord return without error and record nothing",
  "fix": "Ask the user to press Record in Scope View, then run: tcscope.py xae save" }
```

Exit 1.

### A13 — the solution opened through a subst drive — pass

`subst S: C:\work`; the user opened `S:\Scratch\Scratch.sln` by hand.

`tc xae list --solution S:\Scratch\Scratch.sln`

```json
{ "ok": true, "solution": "S:\\Scratch\\Scratch.sln", "project": "TwinCAT Measurement Project1",
  "project_path": "S:\\Scratch\\TwinCAT Measurement Project1\\TwinCAT Measurement Project1.tcmproj",
  "scopes": [ { "name": "ScopeA.tcscopex", "path": "S:\\Scratch\\TwinCAT Measurement Project1\\ScopeA.tcscopex" },
              { "name": "ScopeB.tcscopex", "path": "S:\\Scratch\\TwinCAT Measurement Project1\\ScopeB.tcscopex" },
              { "name": "ScopeB2.tcscopex", "path": "S:\\Scratch\\TwinCAT Measurement Project1\\ScopeB2.tcscopex" } ] }
```

`tc xae add C:\work\gen\ScopeC.tcscopex --solution S:\Scratch\Scratch.sln`

```json
{ "ok": true, "item": "ScopeC.tcscopex", "path": "S:\\Scratch\\TwinCAT Measurement Project1\\ScopeC.tcscopex",
  "project": "TwinCAT Measurement Project1", "project_saved": true }
```

Both exit 0. The `.tcmproj` gained only the relative `<Content Include="ScopeC.tcscopex">`; no
`C:\` or `S:\` path was written anywhere in it. Nothing came back as `C:\…` where `S:\…` was
expected. `subst S: /d` afterwards.

### A14 — dialogs throughout A2–A13 — pass for the tool; other dialogs listed

Reload prompts: only the ones A6 provoked (one per change to ScopeA, plus one for restoring it).
No verb raised a dialog. Dialogs and changes that did not come from the tool:

| After | What |
|---|---|
| A6, first attempt | XAE showed a New Project window (WPF, class `HwndWrapper[…]`) — origin unclear, likely a stray click. `xae list` answered ok while it was open; the dialog check does not see WPF windows. |
| A6, XAE reopened | A `VSSettings/` folder appeared in the Measurement project folder (untracked). |
| A10 and A13, closing XAE | "Save changes to the following items? Scratch.sln / TwinCAT Measurement Project1 / ScopeB2.tcscopex*" — Yes pressed. See Surprises. |
| A13, after reopening | Two `.xti` files of another, unrelated engineering project were open in the scratch XAE as loose XML documents ("Miscellaneous Files"). Not opened by the tool, which only reads; closed without saving. |

## Part B — which pragmas hide a symbol

### B1 — build

Build → Build Solution succeeded. XAE's Error List (read through the DTE) held 0 errors and 0
warnings: the compiler accepted every pragma in every position of §3.

### B2 — the `.tmc`

```
--- symbols under MAIN
MAIN.bReset
MAIN.fbAddMethod
MAIN.fbHideType
MAIN.fbNoSymType
MAIN.fbOneHidden
MAIN.fbPlain
MAIN.fbSuite
MAIN.fbSymNoneType
MAIN.nCounter
MAIN.nOpcOff
MAIN.nPlain
MAIN.nSymbolNone
MAIN.nSymbolRead
--- DataType FB_Probe
nValue  props:
--- DataType FB_ProbeHide
nValue  props:
--- DataType FB_ProbeNoSym
nValue  props:
--- DataType FB_ProbeSymNone
nValue  props:
--- DataType FB_ProbeOneHidden
nVisible  props:
--- full DataType FB_ProbeOneHidden
<DataType><Name>FB_ProbeOneHidden</Name><BitSize>128</BitSize><SubItem><Name>nVisible</Name><Type>UDINT</Type><BitSize>32</BitSize><BitOffs>64</BitOffs></SubItem><Properties><Property><Name>PouType</Name><Value>FunctionBlock</Value></Property></Properties></DataType>
--- Properties of MAIN.nHide / MAIN.fbOneHidden symbols
MAIN.nHide : no symbol
MAIN.fbOneHidden :            (no <Properties>)
```

`bReset`, `fbAddMethod`, `fbSuite`, `nCounter` belong to the solution's existing code.

The pragmas that did not remove a symbol are recorded as properties:

```
MAIN.nPlain         : (no <Properties>)
MAIN.nSymbolNone    : <Properties><Property><Name>symbol</Name><Value>none</Value></Property></Properties>
MAIN.nSymbolRead    : <Properties><Property><Name>symbol</Name><Value>read</Value></Property></Properties>
MAIN.nOpcOff        : <Properties><Property><Name>OPC.UA.DA</Name><Value>0</Value></Property></Properties>
MAIN.fbHideType     : (no <Properties>)
MAIN.fbNoSymType    : (no <Properties>)
MAIN.fbSymNoneType  : (no <Properties>)

DataType FB_Probe        : <DataType><Name>FB_Probe</Name><BitSize>128</BitSize><SubItem><Name>nValue</Name><Type>UDINT</Type><BitSize>32</BitSize><BitOffs>64</BitOffs></SubItem><Properties><Property><Name>PouType</Name><Value>FunctionBlock</Value></Property></Properties></DataType>
DataType FB_ProbeHide    : <DataType><Name>FB_ProbeHide</Name><BitSize>128</BitSize><SubItem><Name>nValue</Name><Type>UDINT</Type><BitSize>32</BitSize><BitOffs>64</BitOffs></SubItem><Properties><Property><Name>PouType</Name><Value>FunctionBlock</Value></Property><Property><Name>hide</Name></Property></Properties></DataType>
DataType FB_ProbeNoSym   : <DataType><Name>FB_ProbeNoSym</Name><BitSize>128</BitSize><SubItem><Name>nValue</Name><Type>UDINT</Type><BitSize>32</BitSize><BitOffs>64</BitOffs></SubItem><Properties><Property><Name>PouType</Name><Value>FunctionBlock</Value></Property><Property><Name>tc_no_symbol</Name></Property></Properties></DataType>
DataType FB_ProbeSymNone : <DataType><Name>FB_ProbeSymNone</Name><BitSize>128</BitSize><SubItem><Name>nValue</Name><Type>UDINT</Type><BitSize>32</BitSize><BitOffs>64</BitOffs></SubItem><Properties><Property><Name>PouType</Name><Value>FunctionBlock</Value></Property><Property><Name>symbol</Name><Value>none</Value></Property></Properties></DataType>
```

### B3 — `checkscope --tmc`

ScopeP over all 13 probe channels (10 ms, 5 s). `checkscope --tmc`: exit 1, checked 13,
resolved 9.

Problems (each worded as below, with the variable's own name):

```
MAIN.nHide: MAIN.nHide is not in the compiled program, so Scope would report an unknown symbol. A typo, a renamed variable, a symbol of another PLC runtime - pass that one's .tmc too - or one a pragma keeps out of the symbol table, such as {attribute 'hide'} or {attribute 'tc_no_symbol'}.
MAIN.nTcNoSymbol: MAIN.nTcNoSymbol is not in the compiled program, ...
MAIN.nTcNoSymbolCC: MAIN.nTcNoSymbolCC is not in the compiled program, ...
MAIN.fbOneHidden.nHidden: nHidden (no such member of FB_ProbeOneHidden) is not in the compiled program, ...
```

Warnings: the fixed 5 s window warning (no trigger, no restart), as designed.

`tmc: { "files": [ "C:\\work\\Scratch\\Scratch\\PLC1\\PLC1.tmc" ], "checked": 13, "resolved": 9 }`

### B4 — what is really reachable

**(a) Target Browser**, port 851, `MAIN` expanded (13 sub-items): `bReset`, `fbAddMethod` (5
members), `fbHideType → nValue`, `fbNoSymType → nValue`, `fbOneHidden → nVisible` only,
`fbPlain → nValue`, `fbSuite`, `fbSymNoneType → nValue`, `nCounter`, `nOpcOff`, `nPlain`,
`nSymbolNone`, `nSymbolRead`. Absent: `nHide`, `nTcNoSymbol`, `nTcNoSymbolCC`,
`fbOneHidden.nHidden`. The type-level pragmas appear only in the *Attributes (Type)* column
(`{ hide }`, `{ tc_no_symbol }`, `{ symbol : none }`); instance attributes show
`{ symbol : none }`, `{ symbol : read }`, `{ OPC.UA.DA : 0 }` on the three variables.

**(b) Recording.** ScopeP was added with `xae add` (no dialog, `project_saved: true`). On Record,
Scope View's Error List showed exactly one error and recorded nothing:

```
'TwinCAT Measurement' (08:10:47.355): 'TwinCAT Scope View' (16-11-2026 08:10:47): Symbolname could not be found for channel: '"nHide' (MAIN.nHide)'
```

Only the first unknown symbol is reported; per the user, Scope View can name the next one only
after the first is removed. So ScopeP2 was generated over the nine channels B3 resolved, added
with `xae add`, recorded by the user (5 s, stopped by itself) and saved with `xae save ScopeP2`
(177,939 bytes). `manifest`: 501 rows, 5.0 s, 100 Hz, 0 gaps, every channel UINT32 with no NaN:

| symbol_name | data_type | nan_fraction | constant |
|---|---|---|---|
| MAIN.nPlain | UINT32 | 0.00 | False |
| MAIN.nSymbolNone | UINT32 | 0.00 | False |
| MAIN.nSymbolRead | UINT32 | 0.00 | False |
| MAIN.nOpcOff | UINT32 | 0.00 | False |
| MAIN.fbPlain.nValue | UINT32 | 0.00 | False |
| MAIN.fbHideType.nValue | UINT32 | 0.00 | False |
| MAIN.fbNoSymType.nValue | UINT32 | 0.00 | False |
| MAIN.fbSymNoneType.nValue | UINT32 | 0.00 | False |
| MAIN.fbOneHidden.nVisible | UINT32 | 0.00 | False |

`cleanup --solution $sln` then deleted the `.svdx`, its two cache files and `Recordings`.

### Result table

| Variable | Pragma | Compiles? | In `.tmc` symbols / as SubItem? | `checkscope --tmc` | Target Browser shows it? | Scope records it? |
|---|---|---|---|---|---|---|
| MAIN.nPlain | none | yes | yes | ok | yes | yes |
| MAIN.nHide | `hide` | yes | no | problem | no | no — *Symbolname could not be found* |
| MAIN.nTcNoSymbol | `tc_no_symbol` | yes | no | problem | no | not recorded (ScopeP stopped at nHide); unreachable by the Target Browser |
| MAIN.nTcNoSymbolCC | `TcNoSymbol` | yes | no | problem | no | as above |
| MAIN.nSymbolNone | `symbol := 'none'` | yes | yes, property symbol=none | ok | yes | yes |
| MAIN.nSymbolRead | `symbol := 'read'` | yes | yes, property symbol=read | ok | yes | yes |
| MAIN.nOpcOff | `OPC.UA.DA := '0'` | yes | yes, property OPC.UA.DA=0 | ok | yes | yes |
| MAIN.fbPlain.nValue | none | yes | yes / SubItem | ok | yes | yes |
| MAIN.fbHideType.nValue | `hide` on the FB declaration | yes | yes / SubItem; DataType property hide | ok | yes | yes |
| MAIN.fbNoSymType.nValue | `tc_no_symbol` on the FB declaration | yes | yes / SubItem; DataType property tc_no_symbol | ok | yes | yes |
| MAIN.fbSymNoneType.nValue | `symbol := 'none'` on the FB declaration | yes | yes / SubItem; DataType property symbol=none | ok | yes | yes |
| MAIN.fbOneHidden.nVisible | none (sibling hidden) | yes | yes / SubItem | ok | yes | yes |
| MAIN.fbOneHidden.nHidden | `hide` on the member | yes | no SubItem | problem | no | not recorded; unreachable by the Target Browser |

## Answers

**1. Are `xae add | save | list`, `recordings` and `cleanup` fit for use?** Yes, for the path a
user normally takes. Add, list, save, the project recordings setting, cleanup and the subst drive
all worked on a real XAE with no dialog and the expected git trace, and recordings round-tripped
through `checkscope` / `ingest` / `manifest`. One fail should be fixed before relying on the verbs
in front of users: A6 — with an XAE dialog open, every verb waits 30 s and then reports "no XAE …
run both at the same level", which sends the user after elevation instead of the dialog. It
changes nothing and does no harm, so it does not block use. Minor: cleanup leaves an empty parent
folder (`Data\` in A11).

**2. Which pragmas keep a symbol from Scope?** On TC3.1 build 4024.55: on a variable,
`{attribute 'hide'}`, `{attribute 'tc_no_symbol'}` and `{attribute 'TcNoSymbol'}` each remove the
ADS symbol — absent from the `.tmc`, absent from the Target Browser, and Scope reports
*Symbolname could not be found*. `{attribute 'symbol' := 'none'}` does not: the variable stays in
the `.tmc` (with property symbol=none), in the Target Browser, and records normally.
`{attribute 'symbol' := 'read'}` and `{attribute 'OPC.UA.DA' := '0'}` do not affect Scope. A
pragma on a function block's declaration — `hide`, `tc_no_symbol` or `symbol := 'none'` — hides
neither its instances nor their members: all three instances' `nValue` recorded. `hide` on a
member removes that member.

**3. Does a hidden member still appear as a SubItem in the `.tmc`?** No. `nHidden` has no
SubItem in `FB_ProbeOneHidden`; only `nVisible` does. `checkscope --tmc` therefore already flags
it ("no such member of FB_ProbeOneHidden"), and no new rule is needed for this case. The only
trace in the XML is the type's size: `<BitSize>128</BitSize>` while the last SubItem ends at
BitOffs 64 + BitSize 32 = 96. For pragmas on a block's declaration the `.tmc` carries
`<Property><Name>hide</Name></Property>` (or `tc_no_symbol`, `symbol`/`none`) on the DataType —
but those instances proved reachable, so `checkscope` is right not to flag them.

## Surprises

- **Default NetId does not reach a local runtime.** A scope generated with the default
  `0.0.0.0.0.0` failed in Scope View with *Target not connected: '0.0.0.0.0.0 Port: 851'*, on the
  PC that runs the target. Every recording needed `newscope --netid`.
- **Scope View names only the first unknown symbol.** With four unreachable channels it reported
  only `nHide`. `checkscope --tmc` listed all four at once — the faster loop.
- **Every recording leaves its scope unsaved.** After a recording, closing XAE asks to save
  `ScopeB2.tcscopex*`. Saving rewrites the file in XAE's own format: 21,070 bytes against the
  generated 14,526. `checkscope` still passed on it (same channel, rate, window and target).
- **The dialog check sees `#32770` boxes only.** XAE's WPF New Project window was open while
  `xae list` answered ok. Harmless for a read, but the same blind spot as A6's.
- Reopening XAE creates `VSSettings/` in the Measurement project folder; it shows as untracked in
  the user's `git status`.
- **Two saves of the same scope differ in size.** The two ScopeB2 recordings, both 1001 rows of
  one UINT32 channel, were 29,692 and 31,102 bytes. Do not compare recordings by size.
- `doctor` reports `ok: false` when the analysis packages are missing for plain Python even though
  `uv` is present and installs them on demand — reads as a failure on a working setup.
- `xae list` takes ~0.7 s, `xae add` ~0.9–1.0 s, `xae save` ~1.2 s, each in a fresh PowerShell
  process.
