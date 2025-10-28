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
    [int]$PollAttempts = 6
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

function Get-HealthSnapshot {
    try {
        return Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 10
    } catch {
        Write-Host "[test] Warning: unable to query /health - $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

function Get-ContainerSummary {
    param($Health)

    if ($Health -and $Health.containers) {
        return @($Health.containers | ForEach-Object {
            $notesValue = $null
            if ($_.PSObject.Properties.Name -contains 'error') {
                $notesValue = $_.error
            }
            $restartValue = $null
            if ($_.PSObject.Properties.Name -contains 'restart_count') {
                $restartValue = $_.restart_count
            }
            [PSCustomObject]@{
                name = $_.name
                status = $_.status
                health = $_.health
                restart = $restartValue
                started_at = $_.started_at
                notes = $notesValue
            }
        })
    }

    $result = @()
    try {
        $raw = & docker ps --format "{{json .}}" 2>$null
        foreach ($line in $raw) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $obj = $line | ConvertFrom-Json
                $result += [PSCustomObject]@{
                    name = $obj.Names
                    status = $obj.Status
                    health = $obj.Health
                    restart = $obj.RestartCount
                    started_at = $obj.RunningFor
                    notes = $obj.Ports
                }
            } catch {}
        }
    } catch {}
    return $result
}

function Show-RestartSummary {
    param($Containers)

    Write-Host "[test] Container summary" -ForegroundColor Cyan
    if (-not $Containers -or $Containers.Count -eq 0) {
        Write-Host "  (no container data available)"
        return
    }

    foreach ($container in $Containers) {
        $statusValue = if ($container.status) { $container.status } else { 'unknown' }
        $statusText = "status={0}" -f $statusValue
        $healthText = if ($container.health) { " health={0}" -f $container.health } else { "" }
        $restartText = if ($null -ne $container.restart) { " restarts={0}" -f $container.restart } else { "" }
        $noteText = if ($container.notes) { " notes={0}" -f $container.notes } else { "" }
        Write-Host ("  {0,-32} {1}{2}{3}{4}" -f $container.name, $statusText, $healthText, $restartText, $noteText)
    }
}

function Write-TestReport {
    param($Health, $Containers)

    $report = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('o')
        api_health = $Health
        containers = $Containers
    }

    $reportDir = Join-Path $repoRoot 'reports'
    if (-not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir | Out-Null
    }
    $reportPath = Join-Path $reportDir 'test-stack-report.json'
    $report | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8
    Write-Host "[test] Report written to $reportPath" -ForegroundColor Cyan
}

function Invoke-QuickSimulationPulse {
    param(
        [int]$StepMinutes = 5,
        [double]$DurationHours = 0.25
    )

    try {
        $body = @{
            step_minutes = $StepMinutes
            speed_multiplier = 3600
            spend_ratio = 0.1
            expansion_cost_per_gpu_cents = 40000
            electricity_cost_per_kwh = 0.065
            gpu_wattage_w = 240
            continuous = $false
            duration_hours = $DurationHours
        } | ConvertTo-Json -Depth 3

        Invoke-RestMethod -Uri 'http://localhost:8000/simulate' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10 | Out-Null
        return $true
    } catch {
        Write-Host "[test] Warning: unable to trigger simulation pulse - $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

$services = @('db','minio','api','web','agent')

if ($Rebuild) {
    Write-Host "[test] Rebuilding containers..." -ForegroundColor Cyan
    Invoke-Compose build @services | Out-Null
    Invoke-Compose up -d @services | Out-Null
} else {
    Write-Host "[test] Ensuring containers are running..." -ForegroundColor Cyan
    $running = @()
    try {
        $running = & docker compose ps --services --filter "status=running" 2>$null
    } catch {}
    $missing = @($services | Where-Object { $_ -notin $running })
    if ($missing.Length -gt 0) {
        Write-Host "[test] Starting missing services: $($missing -join ', ')" -ForegroundColor Cyan
        Invoke-Compose up -d @missing | Out-Null
    } else {
        Write-Host "[test] All requested services already running." -ForegroundColor Cyan
    }
}

$composeStatus = & docker compose ps 2>$null
if ($LASTEXITCODE -eq 0 -and $composeStatus) {
    $stuck = $composeStatus | Select-String -Pattern 'unhealthy|Restarting'
    if ($stuck) {
        Write-Host "[test] Warning: detected unhealthy or restarting service - attempting recovery" -ForegroundColor Yellow
        & docker compose restart | Out-Null
        Start-Sleep -Seconds 5
    }
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
    Write-Host "[test] Metrics static after initial polling; triggering quick simulation pulse..." -ForegroundColor Yellow
    $pulseStarted = Invoke-QuickSimulationPulse -StepMinutes 5 -DurationHours 0.15
    if ($pulseStarted) {
        $waitSeconds = [Math]::Max([int]$PollIntervalSeconds * 2, 6)
        Start-Sleep -Seconds $waitSeconds
        $next = Get-RegionSnapshot
        if (Has-MetricChange $baseline $next) {
            $changed = $true
        }
        try {
            Invoke-RestMethod -Uri 'http://localhost:8000/simulate/stop' -Method Post -TimeoutSec 5 | Out-Null
        } catch {}
    }
}

if (-not $changed) {
    throw "Metrics did not change after $PollAttempts polls (even after simulation pulse)."
}

$web = Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing -TimeoutSec 15
if ($web.StatusCode -ne 200) {
    throw "Web UI returned status $($web.StatusCode)"
}

if ($web.Content -notmatch 'GPU Reseller Regions') {
    throw "Web UI did not render expected dashboard heading."
}

Write-Host "[test] PASS: Live metrics verified" -ForegroundColor Green

$healthSnapshot = Get-HealthSnapshot
$containerSnapshot = Get-ContainerSummary $healthSnapshot
Show-RestartSummary $containerSnapshot
Write-TestReport -Health $healthSnapshot -Containers $containerSnapshot

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
