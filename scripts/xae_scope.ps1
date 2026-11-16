<#
.SYNOPSIS
Drives a scope through the open TwinCAT XAE's Automation Interface: list the scopes in its
Measurement project, add a generated .tcscopex to it, save a held recording as .svdx, and -
only when the user asked for it - press Start Record, wait for the scope to stop by itself, and
save.

.DESCRIPTION
tcscope.py's `xae` verbs call this, one process per operation; run it directly only to debug.
Windows PowerShell 5.1, at the same elevation as XAE: an elevated XAE is invisible to a
non-elevated shell, and the other way round.

  xae_scope.ps1 list -Solution <.sln> [-Project <name>]
  xae_scope.ps1 add  -Solution <.sln> -Scope <file.tcscopex> [-Project <name>]
  xae_scope.ps1 save -Solution <.sln> -Item <name.tcscopex> -Out <file.svdx> [-Project <name>]
  xae_scope.ps1 record -Solution <.sln> -Item <name.tcscopex> -Out <file.svdx> -TimeoutS <s> [-Project <name>]

Prints one JSON object. Exit 0 done, 1 refused or failed, 2 bad arguments.

It touches only the XAE whose open solution is -Solution, refuses while that XAE shows a
dialog - checked before any COM call, because XAE rejects calls while one is open - and never
writes into the Measurement project folder itself: a file rewritten there
raises XAE's "changed outside the environment" prompt, and a later save can put XAE's old copy
back over it. The add goes through the DTE, which copies the file in. record presses only the
'Start Record' button of the 'TwinCAT 3 Scope' toolbar, found by exact name, and never Stop
Record. Field evidence for every call: evals/field-review-xae-scope.md and
evals/field-review-xae-acceptance.md.
#>
param(
    [Parameter(Position = 0)][string] $Verb,
    [string] $Solution,
    [string] $Project,
    [string] $Scope,
    [string] $Item,
    [string] $Out,
    [double] $TimeoutS = 0
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }   # tcscope.py reads UTF-8

function Emit($obj, [int] $code) {
    Write-Output ($obj | ConvertTo-Json -Depth 5 -Compress)
    exit $code
}
# Filled in by record as it goes, so a refusal half-way still says what was pressed and seen.
$script:Context = [ordered]@{}
function Fail([string] $msg, [string] $fix = $null, [int] $code = 1) {
    $o = [ordered]@{ ok = $false; error = $msg }
    if ($fix) { $o.fix = $fix }
    foreach ($k in $script:Context.Keys) { $o[$k] = $script:Context[$k] }
    Emit $o $code
}
function Usage([string] $msg) {
    Fail $msg 'xae_scope.ps1 list|add|save|record -Solution <.sln> [-Scope <file.tcscopex>] [-Item <name.tcscopex> -Out <file.svdx>] [-TimeoutS <s>] [-Project <name>]' 2
}
function Full([string] $p) { [IO.Path]::GetFullPath($p) }
function Test-Inside([string] $path, [string] $folder) {
    $f = (Full $folder).TrimEnd('\') + '\'
    (Full $path).StartsWith($f, [StringComparison]::OrdinalIgnoreCase)
}

# ---- arguments, checked before any COM work --------------------------------------------------

if ($Verb -notin @('list', 'add', 'save', 'record')) { Usage "unknown verb '$Verb'" }
if (-not $Solution) { Usage '-Solution is required' }
if ([IO.Path]::GetExtension($Solution) -ne '.sln') { Usage "-Solution must name the .sln file, got '$Solution'" }
if (-not (Test-Path -LiteralPath $Solution -PathType Leaf)) { Fail "solution $Solution does not exist" }
$Solution = Full $Solution
if ($Verb -eq 'add') {
    if (-not $Scope) { Usage 'add needs -Scope <file.tcscopex>' }
    if ([IO.Path]::GetExtension($Scope) -ne '.tcscopex') { Usage "-Scope must be a .tcscopex, got '$Scope'" }
    if (-not (Test-Path -LiteralPath $Scope -PathType Leaf)) { Fail "scope $Scope does not exist" }
    $Scope = Full $Scope
}
if ($Verb -in @('save', 'record')) {
    if (-not $Item) { Usage "$Verb needs -Item <name.tcscopex>" }
    if (-not $Out) { Usage "$Verb needs -Out <file.svdx>" }
    if ([IO.Path]::GetExtension($Out) -ne '.svdx') { Usage "-Out must be a .svdx, got '$Out'" }
    $Out = Full $Out
    if (-not (Test-Path -LiteralPath (Split-Path $Out) -PathType Container)) { Fail "the folder of $Out does not exist" }
    if (Test-Path -LiteralPath $Out) { Fail "refusing to overwrite $Out" }
}
if ($Verb -eq 'record' -and -not ($TimeoutS -gt 0)) {
    Usage 'record needs -TimeoutS <seconds>: how long to wait for the scope to stop by itself'
}

# ---- COM and Win32 plumbing ------------------------------------------------------------------

Add-Type -TypeDefinition @"
using System; using System.Text; using System.Collections.Generic;
using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes;

// Retries a call XAE rejects while busy (SERVERCALL_RETRYLATER) for up to 30 s.
[ComImport, Guid("00000016-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IOleMessageFilter {
    [PreserveSig] int HandleInComingCall(int t, IntPtr h, int ti, IntPtr i);
    [PreserveSig] int RetryRejectedCall(IntPtr h, int ti, int r);
    [PreserveSig] int MessagePending(IntPtr h, int ti, int p); }
public class XaeFilter : IOleMessageFilter {
    [DllImport("Ole32.dll")] static extern int CoRegisterMessageFilter(IOleMessageFilter n, out IOleMessageFilter o);
    public static int Rejected = 0;
    public static void Register() { IOleMessageFilter o; CoRegisterMessageFilter(new XaeFilter(), out o); }
    public static void Revoke()   { IOleMessageFilter o; CoRegisterMessageFilter(null, out o); }
    int IOleMessageFilter.HandleInComingCall(int t, IntPtr h, int ti, IntPtr i) { return 0; }
    int IOleMessageFilter.RetryRejectedCall(IntPtr h, int ti, int r) { if (r == 2 && ti < 30000) return 200; Rejected++; return -1; }
    int IOleMessageFilter.MessagePending(IntPtr h, int ti, int p) { return 2; } }

// Every XAE / Visual Studio DTE in the Running Object Table.
public class RotEntry { public string Name; public object Obj; }
public static class Rot {
    [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int r, out IRunningObjectTable t);
    [DllImport("ole32.dll")] static extern int CreateBindCtx(int r, out IBindCtx c);
    public static List<RotEntry> List() {
        var res = new List<RotEntry>(); IRunningObjectTable rot; GetRunningObjectTable(0, out rot);
        IEnumMoniker en; rot.EnumRunning(out en); IMoniker[] m = new IMoniker[1];
        while (en.Next(1, m, IntPtr.Zero) == 0) { try {
            IBindCtx c; CreateBindCtx(0, out c); string n; m[0].GetDisplayName(c, null, out n);
            if (n.StartsWith("!TcXaeShell.DTE.") || n.StartsWith("!VisualStudio.DTE.")) {
                object o; rot.GetObject(m[0], out o); res.Add(new RotEntry { Name = n, Obj = o }); }
        } catch (Exception) { } }
        return res; } }

// The dialogs one process shows, or "" when none:
//  - every visible message box (#32770), with its texts;
//  - any other modal window - a WinForms one such as Scope View's 'Stop Record?', a WPF one
//    such as New Project. A modal window disables the window that owns it, so: when one of the
//    process's visible top-level unowned windows (XAE's main window) is disabled, every visible,
//    enabled window it owns is named. A floating tool window never disables the main window,
//    so it cannot make a verb refuse on its own.
public static class XaeDialogs {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);   // 4 = GW_OWNER
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    public static string Open(int pid) {
        var boxes = new List<string>(); var owned = new List<string>(); bool mainDisabled = false;
        EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
            if (p != (uint)pid || !IsWindowVisible(h)) return true;
            var c = new StringBuilder(256); GetClassName(h, c, 256);
            var t = new StringBuilder(512); GetWindowText(h, t, 512);
            if (c.ToString() != "#32770") {
                if (GetWindow(h, 4) == IntPtr.Zero) { if (!IsWindowEnabled(h)) mainDisabled = true; }
                else if (IsWindowEnabled(h)) owned.Add("'" + t + "' [" + c + "]");
                return true; }
            var sb = new StringBuilder("'" + t + "'");
            EnumChildWindows(h, (ch, l2) => { var ct = new StringBuilder(2048); GetWindowText(ch, ct, 2048);
                if (ct.Length > 0 && IsWindowVisible(ch)) sb.Append(" | " + ct.ToString().Replace("\r", " ").Replace("\n", " "));
                return true; }, IntPtr.Zero);
            boxes.Add(sb.ToString()); return true; }, IntPtr.Zero);
        if (boxes.Count == 0 && mainDisabled) {
            if (owned.Count == 0) owned.Add("a modal window (XAE's main window is disabled)");
            boxes = owned; }
        return string.Join(Environment.NewLine, boxes.ToArray()); } }
"@

$GP = [Reflection.BindingFlags]::GetProperty
$IM = [Reflection.BindingFlags]::InvokeMethod

# The DTE is typed and PowerShell's adapter reads it; the Measurement project and its items
# have no type information, so the adapter returns $null and late-bound IDispatch takes over.
# The leading comma keeps a COM collection from being unrolled.
function Get-Com($o, [string] $name, [object[]] $arguments = $null) {
    $v = $null
    if (-not $arguments) { try { $v = $o.$name } catch { } }
    if ($null -eq $v) {
        try   { $v = [System.__ComObject].InvokeMember($name, $GP, $null, $o, $arguments) }
        catch { $v = [System.__ComObject].InvokeMember($name, $IM, $null, $o, $arguments) }
    }
    , $v
}
# Every argument handed to COM must be a plain .NET value - cast it: [string], [int], [int16].
# A path from Join-Path is a PSObject wrapping the string; passed on as it is, COM receives the
# wrapper and the call fails with InvalidCastException, no dialog, nothing else wrong.
function Invoke-Com($o, [string] $name, [object[]] $arguments) {
    , [System.__ComObject].InvokeMember($name, $IM, $null, $o, $arguments)
}
# Count + Item(i), late-bound first: on an object the adapter cannot see, PowerShell answers
# .Count with its own intrinsic 1. The adapter is the fallback for typed DTE collections.
function Get-ComItems($collection) {
    try { $n = [int][System.__ComObject].InvokeMember('Count', $GP, $null, $collection, $null) }
    catch { $n = [int]$collection.Count }
    for ($i = 1; $i -le $n; $i++) {
        try { $it = [System.__ComObject].InvokeMember('Item', $IM, $null, $collection, @($i)) }
        catch { $it = $collection.Item($i) }
        , $it
    }
}
function Get-InnerError($ex) {
    while ($ex.InnerException) { $ex = $ex.InnerException }
    "$($ex.GetType().Name): $($ex.Message)"
}

# The one XAE whose open solution is exactly $Solution. No other instance is touched: an
# unfiltered lookup could read, and write to, a customer's XAE open beside the scratch one.
# The dialog check runs on each instance's pid - from its ROT name - before its solution is
# asked for: while a dialog is open XAE rejects the call, the message filter retries for 30 s,
# and the instance looked as if it had no solution (field test A6).
function Find-Xae {
    $seen = 0; $blocked = @(); $busy = @()
    foreach ($r in [Rot]::List()) {
        $seen++
        $xaePid = 0
        if ($r.Name -match ':(\d+)$') { $xaePid = [int]$Matches[1] }
        if ($xaePid) {
            $d = [XaeDialogs]::Open($xaePid)
            if ($d) { $blocked += "XAE (process $xaePid) shows: $d"; continue }
        }
        $sln = ''
        $rejected = [XaeFilter]::Rejected
        try { $sln = [string] $r.Obj.Solution.FullName }
        catch {
            $ex = $_.Exception
            while ($ex.InnerException) { $ex = $ex.InnerException }
            $h = $ex.HResult
            # RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER: alive, but refusing calls
            if ([XaeFilter]::Rejected -gt $rejected -or $h -eq -2147418111 -or $h -eq -2147417846) {
                $busy += "process $(if ($xaePid) { $xaePid } else { $r.Name })"
            }
            continue
        }
        if ($sln -and ((Full $sln) -eq $Solution)) {
            if (-not $xaePid) { Fail "cannot read the process id from the ROT entry '$($r.Name)'" }
            return [pscustomobject]@{ Dte = $r.Obj; Pid = $xaePid; Seen = $seen }
        }
    }
    if ($blocked.Count) {
        Fail ("no XAE that could be asked has $Solution open, and $($blocked.Count) could not be asked " +
              "because it shows a dialog, not touching it: " + ($blocked -join '; ')) `
            'Answer the dialog in XAE yourself, then run the command again.'
    }
    if ($busy.Count) {
        Fail ("no XAE that answered has $Solution open; $($busy.Count) did not answer within 30 s " +
              "(busy, or showing a dialog this check cannot see): " + ($busy -join ', ')) `
            'Wait until XAE is idle and answer any dialog it shows, then run the command again.'
    }
    Fail "no XAE has $Solution open ($seen XAE/Visual Studio instance(s) checked)" `
        'Open the solution in TwinCAT XAE. An XAE running as administrator is invisible to a shell that is not, and the other way round: run both at the same level.'
}
function Assert-NoDialog($xae, [string] $when = '') {
    $d = [XaeDialogs]::Open($xae.Pid)
    if ($d) {
        Fail "XAE shows a dialog$when, not touching it: $d" 'Answer the dialog in XAE yourself, then run the command again.'
    }
}
function Find-MeasurementProject($dte) {
    $found = @()
    foreach ($p in @(Get-ComItems (Get-Com $dte.Solution 'Projects'))) {
        $full = "$(Get-Com $p 'FullName')"
        if ($full -like '*.tcmproj') { $found += , @{ Obj = $p; Path = $full; Name = "$(Get-Com $p 'Name')" } }
    }
    if ($Project) { $found = @($found | Where-Object { $_.Name -eq $Project }) }
    if ($found.Count -eq 0) {
        if ($Project) { Fail "no Measurement project named '$Project' at the top level of the solution" }
        Fail 'no TwinCAT Measurement project (.tcmproj) at the top level of the solution' `
            'Add one in XAE (File > New > Project > TwinCAT Measurement). One inside a solution folder is not supported yet.'
    }
    if ($found.Count -gt 1) {
        Fail ("the solution holds several Measurement projects: " + (($found | ForEach-Object { $_.Name }) -join ', ')) `
            'Name one with --project.'
    }
    $found[0]
}
function Get-ScopeItems($proj) {
    foreach ($i in @(Get-ComItems (Get-Com $proj.Obj 'ProjectItems'))) {
        $name = "$(Get-Com $i 'Name')"
        if ($name -like '*.tcscopex') { [pscustomobject]@{ Name = $name; Obj = $i } }
    }
}
function Get-ItemPath($i) { "$(Get-Com $i 'FileNames' @([int16] 1))" }
function Find-ScopeItem($proj, [string] $name) {
    $hit = @(Get-ScopeItems $proj | Where-Object { $_.Name -eq $name })
    if ($hit.Count -eq 0) {
        $names = (@(Get-ScopeItems $proj) | ForEach-Object { $_.Name }) -join ', '
        Fail "the Measurement project holds no scope named $name (it holds: $names)"
    }
    $hit[0]
}
# ProjectItem.Object is a ScopeProjectNode that PowerShell's adapter cannot touch at all
# (InvalidCastException even on GetType()), so straight to InvokeMember. Its ScopeProject is the
# Scope View API object.
function Get-ScopeProject($item) {
    $node = [System.__ComObject].InvokeMember('Object', $GP, $null, $item.Obj, $null)
    , [System.__ComObject].InvokeMember('ScopeProject', $GP, $null, $node, $null)
}
# Measured on Scope View 3.4: 60 idle, 50 recording, 70 stopping (about 1 s at the end of a
# full window). No other value has been seen.
$StateNames = @{ 60 = 'idle'; 50 = 'recording'; 70 = 'stopping' }
function Get-ScopeState($sp) { [int][System.__ComObject].InvokeMember('ScopeState', $GP, $null, $sp, $null) }

function Save-Recording($sp, [string] $out) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { [void][System.__ComObject].InvokeMember('SaveData', $IM, $null, $sp, @([string] $out)) }
    catch {
        $err = Get-InnerError $_.Exception
        if ($err -like 'InvalidCastException*') {
            Fail "SaveData failed: $err" 'An argument reached COM as the wrong type - a bug in xae_scope.ps1, not in Scope View: every COM argument must be cast to a plain [string]/[int]. Report it.'
        }
        Fail "SaveData failed: $err" 'Is there a recording held in Scope View for this scope? Press Record, let it stop, then save.'
    }
    # Measured: the file is complete when SaveData returns (30 kB in under 0.2 s). Still,
    # wait up to 60 s for a size that holds still, and never report a growing file as saved.
    $last = -1; $stable = $false
    for ($k = 0; $k -lt 240; $k++) {
        if (Test-Path -LiteralPath $out) {
            $len = (Get-Item -LiteralPath $out).Length
            if ($len -gt 0 -and $len -eq $last) { $stable = $true; break }
            $last = $len
        }
        Start-Sleep -Milliseconds 250
    }
    Assert-NoDialog $xae ' after SaveData'
    if (-not (Test-Path -LiteralPath $out)) {
        Fail "SaveData returned but wrote no file at $out" 'Is there a recording held in Scope View for this scope?'
    }
    if (-not $stable) {
        Fail "$out was still being written after 60 s" 'Wait until its size stops changing, then ingest it by path.'
    }
    $sw.ElapsedMilliseconds
}

# The one button named exactly $name inside the toolbar named exactly 'TwinCAT 3 Scope' of this
# XAE. The same window holds 'Restart TwinCAT System' and 'Restart TwinCAT (Config Mode)': no
# substring, no wildcard, no search outside that toolbar, and anything but one hit is refused.
# The names are English UI text; a localised XAE is refused, never matched loosely.
function Get-ScopeButton([int] $xaePid, [string] $name) {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $A = [System.Windows.Automation.AutomationElement]
    $CT = [System.Windows.Automation.ControlType]
    $PC = [System.Windows.Automation.PropertyCondition]
    $AND = [System.Windows.Automation.AndCondition]
    $tops = $A::RootElement.FindAll('Children', $PC::new($A::ProcessIdProperty, [int] $xaePid))
    $bars = @()
    foreach ($top in $tops) {
        $bars += @($top.FindAll('Descendants', $AND::new($PC::new($A::ControlTypeProperty, $CT::ToolBar),
                                                       $PC::new($A::NameProperty, 'TwinCAT 3 Scope'))))
    }
    if ($bars.Count -ne 1) {
        Fail "expected exactly one 'TwinCAT 3 Scope' toolbar in XAE, found $($bars.Count)" `
            'Open the scope in XAE so its toolbar shows. A localised XAE names it differently and is not supported: press Record yourself.'
    }
    $hits = @($bars[0].FindAll('Children', $AND::new($PC::new($A::ControlTypeProperty, $CT::Button),
                                                     $PC::new($A::NameProperty, $name))))
    if ($hits.Count -ne 1) { Fail "expected exactly one '$name' button in the TwinCAT 3 Scope toolbar, found $($hits.Count)" }
    $hits[0]
}

# ---- verbs -----------------------------------------------------------------------------------

[XaeFilter]::Register()
try {
    $xae = Find-Xae
    Assert-NoDialog $xae
    $proj = Find-MeasurementProject $xae.Dte
    $projDir = Split-Path $proj.Path

    switch ($Verb) {
        'list' {
            $items = @(Get-ScopeItems $proj | ForEach-Object { [ordered]@{ name = $_.Name; path = (Get-ItemPath $_.Obj) } })
            Emit ([ordered]@{ ok = $true; solution = $Solution; project = $proj.Name; project_path = $proj.Path; scopes = $items }) 0
        }
        'add' {
            $leaf = Split-Path $Scope -Leaf
            if (Test-Inside $Scope $projDir) {
                Fail "$Scope is inside the Measurement project folder $projDir" `
                    'Generate the .tcscopex outside the project folder (XAE watches its files), then add it.'
            }
            # A second add of the same name throws COMException 0x800706F4 and leaves the process
            # unable to read the project again, so refuse before the DTE is asked.
            if (@(Get-ScopeItems $proj | Where-Object { $_.Name -eq $leaf }).Count -gt 0) {
                Fail "the Measurement project already holds $leaf" 'Generate it under a new name with newscope -o, then add that.'
            }
            if (Test-Path -LiteralPath (Join-Path $projDir $leaf)) {
                Fail "$leaf already exists in the project folder $projDir, though not as a project item" `
                    'Generate it under a new name with newscope -o, then add that.'
            }
            if (-not (Get-Com $proj.Obj 'Saved')) {
                Fail "the Measurement project $($proj.Name) has unsaved changes" 'Save it in XAE first, so this command saves only its own change.'
            }
            try { $new = Invoke-Com (Get-Com $proj.Obj 'ProjectItems') 'AddFromFileCopy' @($Scope) }
            catch { Fail "XAE refused to add $leaf : $(Get-InnerError $_.Exception)" }
            # Save('') saves the project to its own file. Save() with no argument fails late-bound.
            try { [void](Invoke-Com $proj.Obj 'Save' @('')) }
            catch { Fail "added $leaf but could not save the project: $(Get-InnerError $_.Exception)" 'Save the Measurement project in XAE.' }
            $saved = [bool](Get-Com $proj.Obj 'Saved')
            Assert-NoDialog $xae ' after the add'
            if (-not $saved) { Fail "added $leaf but the project still reports unsaved changes" 'Save the Measurement project in XAE.' }
            $path = Join-Path $projDir $leaf
            try { if ($null -ne $new) { $path = Get-ItemPath $new } } catch { }
            Emit ([ordered]@{ ok = $true; item = $leaf; path = $path; project = $proj.Name; project_saved = $saved }) 0
        }
        'save' {
            if (Test-Inside $Out $projDir) {
                Fail "$Out is inside the Measurement project folder $projDir" 'Save recordings outside the project folder.'
            }
            $sp = Get-ScopeProject (Find-ScopeItem $proj $Item)
            $ms = Save-Recording $sp $Out
            Emit ([ordered]@{ ok = $true; path = $Out; bytes = (Get-Item -LiteralPath $Out).Length; item = $Item;
                    project = $proj.Name; ms = $ms }) 0
        }
        'record' {
            # Only ever run on the user's explicit request (SKILL.md rule 4): it loads the target.
            if (Test-Inside $Out $projDir) {
                Fail "$Out is inside the Measurement project folder $projDir" 'Save recordings outside the project folder.'
            }
            $sp = Get-ScopeProject (Find-ScopeItem $proj $Item)
            $state = Get-ScopeState $sp
            if ($state -ne 60) {
                $what = if ($StateNames.ContainsKey($state)) { $StateNames[$state] } else { 'a state this tool does not know' }
                Fail "$Item is not idle: ScopeState $state ($what)" 'Wait until Scope View has stopped, save any recording it holds, then run again.'
            }
            # The toolbar acts on the active document, not on a named scope.
            $active = ''
            try { $active = [string] $xae.Dte.ActiveDocument.Name } catch { }
            if ($active -ne $Item) {
                Fail "Start Record acts on the active document, which is '$active', not $Item" `
                    "Click into $Item's tab in XAE so it is the active document, then run again."
            }
            $button = Get-ScopeButton $xae.Pid 'Start Record'
            if (-not $button.Current.IsEnabled) { Fail "'Start Record' is not enabled in XAE" 'Is a recording already running, or the runtime stopped?' }
            Assert-NoDialog $xae ' before Start Record'

            $states = New-Object System.Collections.ArrayList
            $pressed = New-Object System.Collections.ArrayList
            $script:Context.pressed = $pressed
            $script:Context.states = $states
            [void]$states.Add([ordered]@{ s = 0.0; state = $state })
            $sw = [Diagnostics.Stopwatch]::StartNew()
            [void]$pressed.Add('Start Record')
            $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()

            # Let it end by itself. Stop Record is never pressed: early, it raises a popup that
            # blocks XAE until a person answers it.
            $started = $false
            while ($true) {
                Start-Sleep -Milliseconds 500
                $t = [math]::Round($sw.Elapsed.TotalSeconds, 1)
                Assert-NoDialog $xae " while recording ($t s after Start Record)"
                $s = Get-ScopeState $sp
                if ($s -ne $states[$states.Count - 1].state) { [void]$states.Add([ordered]@{ s = $t; state = $s }) }
                if (-not $StateNames.ContainsKey($s)) {
                    Fail "ScopeState $s after Start Record, a value this tool does not know; not touching the scope" 'Look at Scope View; save with tcscope.py xae save once it has stopped.'
                }
                if ($s -ne 60) { $started = $true }
                elseif ($started) { break }
                elseif ($t -ge 10) {
                    Fail "Start Record was pressed but $Item never started recording (ScopeState stayed 60 for 10 s)" `
                        "Scope View's Error List says why - often an unknown symbol, or a target that is not connected."
                }
                if ($t -ge $TimeoutS) {
                    Fail "$Item is still recording after $t s (ScopeState $s); left running, Stop Record not pressed" `
                        'Let it stop by itself or press Stop Record in XAE yourself, then run: tcscope.py xae save'
                }
            }
            $recorded = [math]::Round($sw.Elapsed.TotalSeconds, 1)
            $ms = Save-Recording $sp $Out
            Emit ([ordered]@{ ok = $true; path = $Out; bytes = (Get-Item -LiteralPath $Out).Length; item = $Item;
                    project = $proj.Name; ms = $ms; recorded_s = $recorded; states = $states; pressed = $pressed }) 0
        }
    }
} finally {
    [XaeFilter]::Revoke()
}
