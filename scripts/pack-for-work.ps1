<#
.SYNOPSIS
  Prepare a USB / OneDrive bundle so the viewer starts at work without Docker Hub / OMG.

.DESCRIPTION
  Builds the image, saves dist/sysml-spec-qa.tar. Copy that tar + the repo
  (and optionally data\) to the other PC, then run scripts/deploy.ps1.

.EXAMPLE
  .\scripts\pack-for-work.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { (Get-Location).Path }
$Root = (Resolve-Path $Root).Path
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas dans le PATH."
}

$dist = Join-Path $Root 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$tar = Join-Path $dist 'sysml-spec-qa.tar'

Write-Host "Build de sysml-spec-qa:latest ..." -ForegroundColor Cyan
docker compose build
if ($LASTEXITCODE -ne 0) { throw 'docker compose build a echoue' }

Write-Host "Export $tar ..." -ForegroundColor Cyan
if (Test-Path $tar) { Remove-Item $tar -Force }
docker save sysml-spec-qa:latest -o $tar
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tar)) { throw 'docker save a echoue' }

$sizeMb = [math]::Round((Get-Item $tar).Length / 1MB, 1)
$hasIndex = Test-Path (Join-Path $Root 'data\index\spec.sqlite')
$readme = Join-Path $dist 'LIRE-MOI.txt'
@(
    'SysML spec viewer — bundle bureau'
    ''
    'A copier sur USB / OneDrive :'
    "  - tout le dossier git  (docker-compose.yml, scripts, .env.example)"
    "  - dist\sysml-spec-qa.tar  ($sizeMb Mo)"
    $(if ($hasIndex) { '  - data\  (index deja construit = demarrage sans download OMG)' } else { '  - (pas de data\ local : demain le conteneur telechargera les PDF OMG)' })
    ''
    'Demain au taf, dans le dossier du repo :'
    '  powershell -ExecutionPolicy Bypass -File .\scripts\deploy.ps1'
    '  -> http://localhost:3112'
    ''
    'Ne pas deposer data\raw (PDF OMG) sur un partage public.'
) | Set-Content -Path $readme -Encoding UTF8

Write-Host ""
Write-Host "Pret. $sizeMb Mo -> $tar" -ForegroundColor Green
if ($hasIndex) {
    Write-Host "Index local detecte : emporte aussi le dossier data\ pour un boot instantane." -ForegroundColor Green
} else {
    Write-Host "Pas d'index local : demain il faudra omg.org (ou relancer ingest ici d'abord)." -ForegroundColor Yellow
}
Write-Host "Demain :  powershell -ExecutionPolicy Bypass -File .\scripts\deploy.ps1" -ForegroundColor Cyan
Write-Host "Details : $readme"
