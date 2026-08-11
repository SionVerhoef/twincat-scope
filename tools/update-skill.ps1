<#
.SYNOPSIS
    Install or update twincat-scope without using a git submodule.

.DESCRIPTION
    Downloads a release archive and unpacks it into the skill folder your agent
    reads from. For teams who would rather not deal with submodules, or who hit
    the usual submodule trap: a plain `git clone` leaves the folder empty.

    Needs no administrator rights. Writes only inside the target repository.

.PARAMETER Target
    Where the skill folder goes. Defaults to .github/skills\twincat-scope, which
    is where GitHub Copilot in VS Code looks. For Claude Code, pass
    .claude\skills\twincat-scope instead.

.PARAMETER Version
    Release tag to install. Defaults to the latest release.

.EXAMPLE
    .\update-skill.ps1
    .\update-skill.ps1 -Target .claude\skills\twincat-scope -Version v1.0.0
#>
[CmdletBinding()]
param(
    [string]$Target  = ".github/skills/twincat-scope",
    [string]$Version = "latest",
    [string]$Repo    = "SionVerhoef/twincat-scope"
)

$ErrorActionPreference = "Stop"

$uri = if ($Version -eq "latest") {
    "https://api.github.com/repos/$Repo/releases/latest"
} else {
    "https://api.github.com/repos/$Repo/releases/tags/$Version"
}

Write-Host "Looking up $Version release of $Repo..."
try {
    $release = Invoke-RestMethod -Uri $uri -Headers @{ "User-Agent" = "update-skill" }
} catch {
    Write-Error @"
Could not reach the GitHub API: $($_.Exception.Message)

Behind a corporate proxy you may need:
    [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials

If the repository has no releases yet, this script has nothing to download -
use the git submodule install from README.md instead.
"@
    exit 1
}

$tag = $release.tag_name
$zip = Join-Path ([System.IO.Path]::GetTempPath()) "twincat-scope-$tag.zip"
Write-Host "Downloading $tag..."
Invoke-WebRequest -Uri $release.zipball_url -OutFile $zip -Headers @{ "User-Agent" = "update-skill" }

$staging = Join-Path ([System.IO.Path]::GetTempPath()) "twincat-scope-unpack-$([guid]::NewGuid())"
Expand-Archive -Path $zip -DestinationPath $staging -Force

# GitHub wraps zipball contents in a single commit-ish directory.
$inner = Get-ChildItem -Path $staging -Directory | Select-Object -First 1
if (-not $inner) { Write-Error "Archive layout was not what we expected."; exit 1 }

if (Test-Path $Target) {
    Write-Host "Replacing existing $Target"
    Remove-Item -Recurse -Force $Target
}
New-Item -ItemType Directory -Path $Target -Force | Out-Null
Copy-Item -Path (Join-Path $inner.FullName "*") -Destination $Target -Recurse -Force

Remove-Item -Force $zip
Remove-Item -Recurse -Force $staging

Write-Host ""
Write-Host "Installed twincat-scope $tag into $Target" -ForegroundColor Green
Write-Host "Check the environment with:  python3 $Target\scripts\tcscope.py doctor"
