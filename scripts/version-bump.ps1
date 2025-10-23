param(
    [string]$Version = "",
    [string]$Branch = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Path $PSScriptRoot -Parent
$previousLocation = Get-Location

try {
    Set-Location -Path $repoRoot

    if (-not (Test-Path '.git')) {
        throw 'version-bump.ps1 must run from inside a Git repository.'
    }

    if (-not $Version) {
        $timestamp = Get-Date -Format 'yyyy.MM.dd.HHmm'
        $Version = "v$timestamp"
    }

    if (-not $Branch) {
        $Branch = (& git rev-parse --abbrev-ref HEAD).Trim()
        if (-not $Branch) {
            $Branch = 'master'
        }
    }

    Write-Host "[version-bump] Preparing milestone $Version on branch $Branch" -ForegroundColor Cyan

    & git add .
    & git commit -m "Milestone: $Version" --allow-empty
    & git tag -a $Version -m "Auto-tagged milestone $Version"

    $remotes = & git remote
    if ($remotes -contains 'origin') {
        Write-Host "[version-bump] Pushing branch $Branch" -ForegroundColor Cyan
        & git push origin $Branch
        Write-Host "[version-bump] Pushing tag $Version" -ForegroundColor Cyan
        & git push origin $Version
    } else {
        Write-Warning "Remote 'origin' not found. Skipping git push."
    }

    Write-Host "[version-bump] Completed milestone $Version" -ForegroundColor Green
}
finally {
    Set-Location -Path $previousLocation
}
