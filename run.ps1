<#
  run.ps1 — Windows bootstrap for GPU Reseller stack
  - Builds and starts services with Docker Compose
  - Waits for critical ports
  - Prints status and endpoints
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Move to script folder
Set-Location -Path $PSScriptRoot

Write-Host "`nStarting GPU-Reseller stack..." -ForegroundColor Cyan

# Helper: invoke docker compose with fallback to docker-compose
function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    try {
        # Prefer modern 'docker compose'
        & docker @('compose') + $Args
        return
    } catch {
        if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
            & docker-compose @Args
            return
        }
        throw "Neither 'docker compose' nor 'docker-compose' is available. Install Docker Desktop."
    }
}

# Check Docker Desktop availability
Write-Host "Checking Docker Desktop..." -ForegroundColor Yellow
try {
    docker info | Out-Null
} catch {
    Write-Host "Docker Desktop not running. Please start it first." -ForegroundColor Red
    exit 1
}

# Build + start containers
Write-Host "Building and launching containers..." -ForegroundColor Yellow
Invoke-Compose up -d --build | Out-Null

# Function to wait for a TCP port to respond
function Wait-Port([string]$HostName, [int]$Port, [int]$TimeoutSec = 60) {
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

# Wait for critical services
Write-Host "Waiting for Postgres (5432)..." -ForegroundColor Yellow
if (-not (Wait-Port 'localhost' 5432 60)) { Write-Host "Postgres not ready." -ForegroundColor Red; exit 1 }

Write-Host "Waiting for MinIO (9000)..." -ForegroundColor Yellow
if (-not (Wait-Port 'localhost' 9000 60)) { Write-Host "MinIO not ready." -ForegroundColor Red; exit 1 }

# Summary
Write-Host "`nContainer status:" -ForegroundColor Cyan
Invoke-Compose ps

# Endpoint checks via port availability (simple and portable)
Write-Host "`nChecking endpoints..." -ForegroundColor Yellow
$apiOk   = Wait-Port 'localhost' 8000 60
$webOk   = Wait-Port 'localhost' 3000 60
$minioOk = Wait-Port 'localhost' 9001 60

if ($apiOk -and $webOk -and $minioOk) {
    Write-Host "`nAll services healthy! Open in browser:" -ForegroundColor Green
    Write-Host "  API:   http://localhost:8000"
    Write-Host "  Web:   http://localhost:3000"
    Write-Host "  MinIO: http://localhost:9001"
} else {
    Write-Host "`nSome endpoints failed checks. Inspect logs with:" -ForegroundColor Yellow
    Write-Host "  docker compose logs --tail 50"
}

Write-Host "`nDone." -ForegroundColor Cyan

