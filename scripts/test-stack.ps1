<#
  test-stack.ps1 — Automated dev smoke tests for GPU Reseller
  - Ensures docker compose stack is running (optionally rebuilds)
  - Waits for API and web ports
  - Verifies API responds with changing metrics
  - Confirms web UI is reachable
  Usage:
    ./scripts/test-stack.ps1             # reuse existing containers
    ./scripts/test-stack.ps1 -Rebuild    # rebuild containers first
    ./scripts/test-stack.ps1 -Backup     # run tests and archive zip snapshot
#>

param(
    [switch]$Rebuild,
    [switch]$Backup,
    [int]$PollIntervalSeconds = 3,
    [int]$PollAttempts = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -Path $repoRoot

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    try {
        & docker 'compose' @Args
    } catch {
        if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
            & docker-compose @Args
        } else {
            throw "Docker Compose command not found"
        }
    }
}

function Wait-Port ($HostName, $Port, $TimeoutSec = 60) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try {
            $client = New-Object Net.Sockets.TcpClient
            $client.Connect($HostName, $Port)
            $client.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

if ($Rebuild) {
    Write-Host "[test] Rebuilding containers..." -ForegroundColor Cyan
    Invoke-Compose up -d --build | Out-Null
} else {
    Write-Host "[test] Ensuring containers are running..." -ForegroundColor Cyan
    Invoke-Compose up -d | Out-Null
}

Write-Host "[test] Waiting for API (localhost:8000)" -ForegroundColor Yellow
if (-not (Wait-Port 'localhost' 8000 90)) {
    throw "API port 8000 did not become ready"
}

Write-Host "[test] Waiting for Web (localhost:3000)" -ForegroundColor Yellow
if (-not (Wait-Port 'localhost' 3000 90)) {
    throw "Web port 3000 did not become ready"
}

function Get-RegionSnapshot {
    $response = Invoke-RestMethod -Uri 'http://localhost:8000/regions/latest' -TimeoutSec 10
    if (-not $response.regions) {
        throw "API returned no regions payload"
    }
    return $response
}

function Has-MetricChange($previous, $current) {
    foreach ($region in $previous.regions) {
        $match = $current.regions | Where-Object { $_.code -eq $region.code }
        if ($null -ne $match) {
            if ($match.free_gpus -ne $region.free_gpus -or $match.utilization -ne $region.utilization) {
                return $true
            }
        }
    }
    return $false
}

Write-Host "[test] Polling API for live metric changes..." -ForegroundColor Yellow
$baseline = Get-RegionSnapshot
$changed = $false

for ($i = 1; $i -le $PollAttempts; $i++) {
    Start-Sleep -Seconds $PollIntervalSeconds
    $next = Get-RegionSnapshot
    if (Has-MetricChange $baseline $next) {
        $changed = $true
        $baseline = $next
        break
    }
}

if (-not $changed) {
    throw "Metrics did not change after $PollAttempts polls."
}

$web = Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing -TimeoutSec 15
if ($web.StatusCode -ne 200) {
    throw "Web UI returned status $($web.StatusCode)"
}

if ($web.Content -notmatch 'GPU Reseller Regions') {
    throw "Web UI did not render expected dashboard heading."
}

Write-Host "[test] PASS: Live metrics verified" -ForegroundColor Green

function New-CodeBackup {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupDir = Join-Path $repoRoot 'backups'
    if (-not (Test-Path $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir | Out-Null
    }
    $zipPath = Join-Path $backupDir "gpu-reseller-$timestamp.zip"
    $items = Get-ChildItem -Path $repoRoot -Force | Where-Object { $_.Name -ne 'backups' }
    Compress-Archive -Path ($items.FullName) -DestinationPath $zipPath -Force -CompressionLevel Optimal
    Write-Host "[test] Created backup: $zipPath" -ForegroundColor Cyan
}

if ($Backup) {
    Write-Host "[test] Creating repository backup archive..." -ForegroundColor Yellow
    New-CodeBackup
}
