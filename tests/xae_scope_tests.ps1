<#
Tests for scripts/xae_scope.ps1 that need no XAE. CI runs them on windows-latest under Windows
PowerShell 5.1: argument errors, then the compiled COM/Win32 plumbing up to "no XAE has the
solution open". Everything past that needs a real XAE - evals/field-review-xae-scope.md.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\xae_scope_tests.ps1
#>
$ErrorActionPreference = 'Stop'
$helper = Join-Path (Split-Path $PSScriptRoot) 'scripts\xae_scope.ps1'
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('xae_scope_tests_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
$sln = Join-Path $tmp 'Scratch.sln'; Set-Content $sln ''
$scope = Join-Path $tmp 'ScopeC.tcscopex'; Set-Content $scope '<x/>'
$taken = Join-Path $tmp 'taken.svdx'; Set-Content $taken 'x'
$failed = 0

function Run([string[]] $argv) {
    $ErrorActionPreference = 'Continue'   # a child's stderr line must not end the test run
    $out =& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper @argv 2>&1
    $code = $LASTEXITCODE
    $json = $null
    try { $json = ($out | Select-Object -Last 1) | ConvertFrom-Json } catch { }
    [pscustomobject]@{ Code = $code; Json = $json; Raw = ($out -join "`n") }
}
function Check([string] $name, [bool] $ok, $r) {
    if ($ok) { "PASS  $name" } else { "FAIL  $name  -- exit $($r.Code): $($r.Raw)"; $script:failed++ }
}

try {
    $r = Run @('frobnicate', '-Solution', $sln)
    Check 'an unknown verb is a usage error' ($r.Code -eq 2 -and $r.Json.ok -eq $false) $r

    $r = Run @('list')
    Check 'list without -Solution is a usage error' ($r.Code -eq 2 -and $r.Json.error -like '*-Solution*') $r

    $r = Run @('list', '-Solution', (Join-Path $tmp 'Scratch.txt'))
    Check '-Solution must be a .sln' ($r.Code -eq 2) $r

    $r = Run @('list', '-Solution', (Join-Path $tmp 'Missing.sln'))
    Check 'a missing solution is refused' ($r.Code -eq 1 -and $r.Json.error -like '*does not exist*') $r

    $r = Run @('add', '-Solution', $sln, '-Scope', $taken)
    Check 'add refuses anything but a .tcscopex' ($r.Code -eq 2 -and $r.Json.error -like '*.tcscopex*') $r

    $r = Run @('save', '-Solution', $sln, '-Item', 'ScopeC.tcscopex', '-Out', $taken)
    Check 'save refuses to overwrite a file' ($r.Code -eq 1 -and $r.Json.error -like '*refusing to overwrite*') $r

    $r = Run @('save', '-Solution', $sln, '-Item', 'ScopeC.tcscopex', '-Out', (Join-Path $tmp 'nope\a.svdx'))
    Check 'save refuses a folder that does not exist' ($r.Code -eq 1) $r

    # Compiles the C# plumbing, walks the Running Object Table, finds no XAE.
    foreach ($argv in @(@('list', '-Solution', $sln), @('add', '-Solution', $sln, '-Scope', $scope),
                        @('save', '-Solution', $sln, '-Item', 'ScopeC.tcscopex', '-Out', (Join-Path $tmp 'new.svdx')))) {
        $r = Run $argv
        Check "$($argv[0]) without XAE says no XAE has the solution open" ($r.Code -eq 1 -and $r.Json.error -like 'no XAE has*' -and $r.Json.fix) $r
    }
    Check 'nothing was written by the refused save' (-not (Test-Path (Join-Path $tmp 'new.svdx'))) $null
} finally {
    Remove-Item -Recurse -Force $tmp
}
if ($failed) { "$failed check(s) failed"; exit 1 }
'all checks passed'
