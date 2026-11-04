<#
.SYNOPSIS
  Probe: what can the Automation Interface of an open XAE do with a TwinCAT Measurement project?

.DESCRIPTION
  A probe, not a tool. It answers the questions a tool would be built on, and its output is the
  field result. Run it in a Windows PowerShell at the SAME elevation as XAE (an elevated XAE is
  invisible to a non-elevated shell).

  Read-only by default. It lists every XAE in the Running Object Table, the projects of its
  solution, the items of each Measurement project with the COM type each item exposes, and every
  XAE command whose name contains "Scope" (record / stop / save-data commands, if there are any).

  -Add <file> also adds that file to a Measurement project, the way "Add Existing Item" does,
  then reports which DTE call worked and whether XAE showed a dialog. It never records, saves,
  builds or activates anything.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File probe_xae_scope.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File probe_xae_scope.ps1 -Add C:\work\MyScope.tcscopex
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File probe_xae_scope.ps1 -Add .\MyScope.tcscopex -Project "Measurement Project1" -Method AddFromFile
#>
param(
    [string] $Add,
    [string] $Project,
    [ValidateSet('AddFromFileCopy', 'AddFromFile')] [string] $Method = 'AddFromFileCopy',
    [string] $Solution
)
$ErrorActionPreference = 'Stop'

# ROT lookup, message filter and dialog detection: the same approach as twincat-st's xae_edit.ps1.
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
[ComImport, Guid("00000016-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IOleMessageFilter {
    [PreserveSig] int HandleInComingCall(int t, IntPtr h, int ti, IntPtr i);
    [PreserveSig] int RetryRejectedCall(IntPtr h, int ti, int r);
    [PreserveSig] int MessagePending(IntPtr h, int ti, int p);
}
public class ProbeFilter : IOleMessageFilter {
    [DllImport("Ole32.dll")] static extern int CoRegisterMessageFilter(IOleMessageFilter n, out IOleMessageFilter o);
    public static int Rejected = 0;
    public static void Register() { IOleMessageFilter o; CoRegisterMessageFilter(new ProbeFilter(), out o); }
    public static void Revoke()   { IOleMessageFilter o; CoRegisterMessageFilter(null, out o); }
    int IOleMessageFilter.HandleInComingCall(int t, IntPtr h, int ti, IntPtr i) { return 0; }
    int IOleMessageFilter.RetryRejectedCall(IntPtr h, int ti, int r) {
        if (r == 2 && ti < 30000) return 200;
        Rejected++;
        return -1;
    }
    int IOleMessageFilter.MessagePending(IntPtr h, int ti, int p) { return 2; }
}
public class RotEntry { public string Name; public object Obj; }
public static class Rot {
    [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int r, out IRunningObjectTable t);
    [DllImport("ole32.dll")] static extern int CreateBindCtx(int r, out IBindCtx c);
    public static List<RotEntry> List(string[] prefixes) {
        var res = new List<RotEntry>();
        IRunningObjectTable rot; GetRunningObjectTable(0, out rot);
        IEnumMoniker en; rot.EnumRunning(out en);
        IMoniker[] m = new IMoniker[1];
        while (en.Next(1, m, IntPtr.Zero) == 0) {
            try {
                IBindCtx ctx; CreateBindCtx(0, out ctx);
                string name; m[0].GetDisplayName(ctx, null, out name);
                bool wanted = false;
                foreach (string p in prefixes) if (name.StartsWith(p, StringComparison.OrdinalIgnoreCase)) wanted = true;
                if (!wanted) continue;
                object o; rot.GetObject(m[0], out o);
                res.Add(new RotEntry { Name = name, Obj = o });
            } catch (Exception) { }
        }
        return res;
    }
}
public static class ProbeWindows {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    // Visible message boxes (#32770) of one process, with their texts, or "" when none.
    public static string Dialogs(int pid) {
        var boxes = new List<string>();
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p != (uint)pid || !IsWindowVisible(h)) return true;
            var c = new StringBuilder(256); GetClassName(h, c, 256);
            if (c.ToString() != "#32770") return true;
            var t = new StringBuilder(512); GetWindowText(h, t, 512);
            var sb = new StringBuilder("'" + t + "'");
            EnumChildWindows(h, (ch, l2) => {
                var ct = new StringBuilder(2048); GetWindowText(ch, ct, 2048);
                if (ct.Length > 0 && IsWindowVisible(ch)) sb.Append(" | " + ct.ToString().Replace("\r", " ").Replace("\n", " "));
                return true; }, IntPtr.Zero);
            boxes.Add(sb.ToString());
            return true; }, IntPtr.Zero);
        return string.Join(Environment.NewLine, boxes.ToArray());
    }
}
"@
Add-Type -AssemblyName Microsoft.VisualBasic

function Say([string] $text) { [Console]::Out.WriteLine($text) }
function TypeName($o) { try { [Microsoft.VisualBasic.Information]::TypeName($o) } catch { "?($($_.Exception.Message))" } }
function Safe([scriptblock] $read) { try { & $read } catch { "<error: $($_.Exception.Message)>" } }

# Projects, recursing into solution folders (Kind {66A26722-8FB5-11D2-AA7E-00C04F688DDE}).
function Get-AllProjects($projects) {
    foreach ($p in $projects) {
        if ($p.Kind -eq '{66A26722-8FB5-11D2-AA7E-00C04F688DDE}') {
            foreach ($item in $p.ProjectItems) { if ($item.SubProject) { Get-AllProjects @($item.SubProject) } }
        } else { $p }
    }
}

function Show-Items($items, [string] $indent) {
    foreach ($i in $items) {
        $file = Safe { $i.FileNames(1) }
        $obj = Safe { TypeName $i.Object }
        Say "$indent- $($i.Name)  kind=$(Safe { $i.Kind })  object=$obj  file=$file"
        $children = $null; try { if ($i.ProjectItems.Count) { $children = $i.ProjectItems } } catch { }
        if ($children) { Show-Items $children "$indent  " }
    }
}

function Test-Measurement($p) { (Safe { $p.FullName }) -like '*.tcmproj' }

[ProbeFilter]::Register()
try {
    $instances = @([Rot]::List([string[]] @('!TcXaeShell.DTE.', '!VisualStudio.DTE.')))
    Say "probe_xae_scope.ps1 on PowerShell $($PSVersionTable.PSVersion), elevated=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators'))"
    if (-not $instances) {
        $running = @(Get-Process -Name TcXaeShell, devenv -ErrorAction SilentlyContinue)
        Say "No XAE in this shell's Running Object Table. XAE processes running: $($running.Count). If there is one, run this shell at the same elevation as XAE."
        exit 1
    }
    $target = $null
    foreach ($e in $instances) {
        $xaePid = 0; [void][int]::TryParse(($e.Name -replace '^.*:', ''), [ref] $xaePid)
        Say ""
        Say "== $($e.Name.TrimStart('!'))  pid=$xaePid"
        $dlg = [ProbeWindows]::Dialogs($xaePid)
        if ($dlg) { Say "   DIALOG OPEN (calls will be rejected): $dlg"; continue }
        $dte = $e.Obj
        Say "   version: $(Safe { $dte.Version })  edition: $(Safe { $dte.Edition })"
        $sln = Safe { $dte.Solution.FullName }
        Say "   solution: $sln"
        foreach ($p in @(Get-AllProjects $dte.Solution.Projects)) {
            Say "   project: $(Safe { $p.Name })  kind=$(Safe { $p.Kind })  file=$(Safe { $p.FullName })  object=$(Safe { TypeName $p.Object })"
            if (Test-Measurement $p) {
                Show-Items $p.ProjectItems '      '
                if (-not $Solution -or $sln -like "*$Solution*") {
                    if (-not $Project -or $p.Name -eq $Project) { if (-not $target) { $target = [pscustomobject]@{ Dte = $dte; Project = $p; Pid = $xaePid } } }
                }
            }
        }
        Say "   commands containing 'Scope':"
        foreach ($c in $dte.Commands) {
            $n = Safe { $c.Name }
            if ($n -like '*Scope*') { Say "      $n  available=$(Safe { $c.IsAvailable })" }
        }
    }

    if (-not $Add) { exit 0 }

    Say ""
    if (-not $target) { Say "ADD: no Measurement project (*.tcmproj) matched -Project/-Solution."; exit 1 }
    $file = (Resolve-Path -LiteralPath $Add).ProviderPath
    Say "ADD: $file -> $($target.Project.Name) via ProjectItems.$Method"
    try {
        $item = $target.Project.ProjectItems.$Method($file)
        Say "ADD: returned $(TypeName $item)  name=$(Safe { $item.Name })  file=$(Safe { $item.FileNames(1) })  object=$(Safe { TypeName $item.Object })"
    } catch {
        Say "ADD: FAILED: $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 1500
    $dlg = [ProbeWindows]::Dialogs($target.Pid)
    Say "ADD: dialog after the call: $(if ($dlg) { $dlg } else { 'none' })"
    Say "ADD: rejected COM calls: $([ProbeFilter]::Rejected)"
    Say "ADD: project items now:"
    Show-Items $target.Project.ProjectItems '      '
    Say "ADD: project saved? $(Safe { $target.Project.Saved })  (the probe does not save; XAE marks the project unsaved if the add stuck)"
} finally {
    [ProbeFilter]::Revoke()
}
