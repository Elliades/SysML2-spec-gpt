<#
.SYNOPSIS
  Start the spec viewer with Docker (workstation / bureau).

.DESCRIPTION
  Copies .env if missing, loads sysml-spec-qa.tar when the image is absent,
  then `docker compose up` and waits until GET /api/health returns 200.

.EXAMPLE
  .\scripts\deploy.ps1
  .\scripts\deploy.ps1 -Build
#>
[CmdletBinding()]
param(
    [switch]$Build,
    [int]$TimeoutSec = 1200,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { (Get-Location).Path }
$Root = (Resolve-Path $Root).Path
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas dans le PATH. Installe Docker Desktop, ouvre un nouveau terminal, relance."
}

try {
    docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'docker info failed' }
} catch {
    throw "Docker Desktop n'est pas demarre."
}

$envFile = Join-Path $Root '.env'
$example = Join-Path $Root '.env.example'
if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $example)) { throw "Missing .env.example in $Root" }
    Copy-Item $example $envFile
    Write-Host "Cree .env depuis .env.example" -ForegroundColor DarkGray
}

# Docker Compose interpolates the process environment before .env — apply
# the file so a leftover SYSML_HOST_PORT in the shell cannot remap the port.
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
    if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
        Set-Item -Path "Env:$name" -Value $value
    }
}

function Test-Image {
    docker image inspect sysml-spec-qa:latest 1>$null 2>$null
    return ($LASTEXITCODE -eq 0)
}

$tarCandidates = @(
    (Join-Path $Root 'sysml-spec-qa.tar')
    (Join-Path $Root 'dist\sysml-spec-qa.tar')
)
$tar = $tarCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not (Test-Image) -and $tar) {
    Write-Host "Chargement de l'image $tar ..." -ForegroundColor Cyan
    docker load -i $tar
    if ($LASTEXITCODE -ne 0) { throw "docker load a echoue ($tar)" }
}

$compose = @('compose', 'up', '-d')
if ($Build -or -not (Test-Image)) {
    Write-Host "Build + demarrage (premier coup : plusieurs minutes)..." -ForegroundColor Cyan
    $compose += '--build'
} else {
    Write-Host "Demarrage avec l'image locale (sans rebuild)..." -ForegroundColor Cyan
    $compose += '--no-build'
}
& docker @compose
if ($LASTEXITCODE -ne 0) { throw 'docker compose up a echoue' }

$port = 3112
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*SYSML_HOST_PORT\s*=\s*(\d+)') { $port = [int]$Matches[1] }
}
$health = "http://127.0.0.1:$port/api/health"
$open = "http://127.0.0.1:$port/"
$deadline = (Get-Date).AddSeconds($TimeoutSec)
Write-Host "Attente de $health (ingest possible, jusqu'a $TimeoutSec s)..." -ForegroundColor DarkGray

while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 6
        if ($resp.StatusCode -eq 200) {
            Write-Host "OK  $health" -ForegroundColor Green
            Write-Host "Viewer  $open" -ForegroundColor Green
            if (-not $NoBrowser) {
                Start-Process $open
            }
            return
        }
    } catch {
        Start-Sleep -Seconds 4
    }
}

Write-Host "Timeout. Derniers logs :" -ForegroundColor Yellow
docker compose logs --no-color --tail 50
throw "Le viewer n'est pas healthy apres ${TimeoutSec}s. Voir docker compose logs."
