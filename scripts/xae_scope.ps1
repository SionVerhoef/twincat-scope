<#
.SYNOPSIS
Drives a scope through the open TwinCAT XAE's Automation Interface: list the scopes in its
Measurement project, add a generated .tcscopex to it, save a held recording as .svdx.

.DESCRIPTION
tcscope.py's `xae` verbs call this, one process per operation; run it directly only to debug.
Windows PowerShell 5.1, at the same elevation as XAE: an elevated XAE is invisible to a
non-elevated shell, and the other way round.

  xae_scope.ps1 list -Solution <.sln> [-Project <name>]
  xae_scope.ps1 add  -Solution <.sln> -Scope <file.tcscopex> [-Project <name>]
  xae_scope.ps1 save -Solution <.sln> -Item <name.tcscopex> -Out <file.svdx> [-Project <name>]

Prints one JSON object. Exit 0 done, 1 refused or failed, 2 bad arguments.

It touches only the XAE whose open solution is -Solution, refuses while that XAE shows a
dialog, and never writes into the Measurement project folder itself: a file rewritten there
raises XAE's "changed outside the environment" prompt, and a later save can put XAE's old copy
back over it. The add goes through the DTE, which copies the file in. Field evidence for every
call: evals/field-review-xae-scope.md.
#>
param(
    [Parameter(Position = 0)][string] $Verb,
    [string] $Solution,
    [string] $Project,
    [string] $Scope,
    [string] $Item,
    [string] $Out
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }   # tcscope.py reads UTF-8

function Emit($obj, [int] $code) {
    Write-Output ($obj | ConvertTo-Json -Depth 5 -Compress)
    exit $code
}
function Fail([string] $msg, [string] $fix = $null, [int] $code = 1) {
    $o = [ordered]@{ ok = $false; error = $msg }
    if ($fix) { $o.fix = $fix }
    Emit $o $code
}
function Usage([string] $msg) {
    Fail $msg 'xae_scope.ps1 list|add|save -Solution <.sln> [-Scope <file.tcscopex>] [-Item <name.tcscopex> -Out <file.svdx>] [-Project <name>]' 2
}
function Full([string] $p) { [IO.Path]::GetFullPath($p) }
function Test-Inside([string] $path, [string] $folder) {
    $f = (Full $folder).TrimEnd('\') + '\'
    (Full $path).StartsWith($f, [StringComparison]::OrdinalIgnoreCase)
}

# ---- arguments, checked before any COM work --------------------------------------------------

if ($Verb -notin @('list', 'add', 'save')) { Usage "unknown verb '$Verb'" }
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
if ($Verb -eq 'save') {
    if (-not $Item) { Usage 'save needs -Item <name.tcscopex>' }
    if (-not $Out) { Usage 'save needs -Out <file.svdx>' }
    if ([IO.Path]::GetExtension($Out) -ne '.svdx') { Usage "-Out must be a .svdx, got '$Out'" }
    $Out = Full $Out
    if (-not (Test-Path -LiteralPath (Split-Path $Out) -PathType Container)) { Fail "the folder of $Out does not exist" }
    if (Test-Path -LiteralPath $Out) { Fail "refusing to overwrite $Out" }
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

// Visible message boxes (#32770) of one process with their texts, or "" when none.
public static class XaeDialogs {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    public static string Open(int pid) {
        var boxes = new List<string>();
        EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
            if (p != (uint)pid || !IsWindowVisible(h)) return true;
            var c = new StringBuilder(256); GetClassName(h, c, 256); if (c.ToString() != "#32770") return true;
            var t = new StringBuilder(512); GetWindowText(h, t, 512); var sb = new StringBuilder("'" + t + "'");
            EnumChildWindows(h, (ch, l2) => { var ct = new StringBuilder(2048); GetWindowText(ch, ct, 2048);
                if (ct.Length > 0 && IsWindowVisible(ch)) sb.Append(" | " + ct.ToString().Replace("\r", " ").Replace("\n", " "));
                return true; }, IntPtr.Zero);
            boxes.Add(sb.ToString()); return true; }, IntPtr.Zero);
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
function Find-Xae {
    $seen = 0
    foreach ($r in [Rot]::List()) {
        $seen++
        $sln = ''
        try { $sln = [string] $r.Obj.Solution.FullName } catch { }
        if ($sln -and ((Full $sln) -eq $Solution)) {
            if ($r.Name -notmatch ':(\d+)$') { Fail "cannot read the process id from the ROT entry '$($r.Name)'" }
            return [pscustomobject]@{ Dte = $r.Obj; Pid = [int]$Matches[1]; Seen = $seen }
        }
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
            $hit = @(Get-ScopeItems $proj | Where-Object { $_.Name -eq $Item })
            if ($hit.Count -eq 0) {
                $names = (@(Get-ScopeItems $proj) | ForEach-Object { $_.Name }) -join ', '
                Fail "the Measurement project holds no scope named $Item (it holds: $names)"
            }
            # ProjectItem.Object is a ScopeProjectNode that PowerShell's adapter cannot touch at all
            # (InvalidCastException even on GetType()), so straight to InvokeMember.
            $sw = [Diagnostics.Stopwatch]::StartNew()
            try {
                $node = [System.__ComObject].InvokeMember('Object', $GP, $null, $hit[0].Obj, $null)
                $sp =[System.__ComObject].InvokeMember('ScopeProject', $GP, $null, $node, $null)
                [void][System.__ComObject].InvokeMember('SaveData', $IM, $null, $sp, @($Out))
            } catch { Fail "SaveData failed: $(Get-InnerError $_.Exception)" 'Is there a recording held in Scope View for this scope? Press Record, let it stop, then save.' }
            # Measured: the file is complete when SaveData returns (30 kB in under 0.2 s). Still,
            # wait up to 60 s for a size that holds still, and never report a growing file as saved.
            $last = -1; $stable = $false
            for ($k = 0; $k -lt 240; $k++) {
                if (Test-Path -LiteralPath $Out) {
                    $len = (Get-Item -LiteralPath $Out).Length
                    if ($len -gt 0 -and $len -eq $last) { $stable = $true; break }
                    $last = $len
                }
                Start-Sleep -Milliseconds 250
            }
            Assert-NoDialog $xae ' after SaveData'
            if (-not (Test-Path -LiteralPath $Out)) {
                Fail "SaveData returned but wrote no file at $Out" 'Is there a recording held in Scope View for this scope?'
            }
            if (-not $stable) {
                Fail "$Out was still being written after 60 s" 'Wait until its size stops changing, then ingest it by path.'
            }
            Emit ([ordered]@{ ok = $true; path = $Out; bytes = (Get-Item -LiteralPath $Out).Length; item = $Item;
                    project = $proj.Name; ms = $sw.ElapsedMilliseconds }) 0
        }
    }
} finally {
    [XaeFilter]::Revoke()
}
