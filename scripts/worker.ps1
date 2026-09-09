<#
.SYNOPSIS
  SysML spec QA worker - keeps the local viewer/API alive for Cursor MCP links.

.DESCRIPTION
  Starts `python -m sysml_spec_qa serve` (FastAPI on 127.0.0.1) with a restart loop.
  Logs to data/logs/worker.log. Safe to run from a scheduled task or Startup shortcut.

.EXAMPLE
  .\scripts\worker.ps1
  .\scripts\worker.ps1 -Port 8797
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [int]$Port = 0,
    [string]$HostBind = '0.0.0.0',
    [int]$RestartSeconds = 8
)

$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { 'C:\workspace\sysml-spec-qa' }
}
$Root = (Resolve-Path $Root).Path

if ($Port -le 0) {
    $Port = if ($env:SYSML_VIEWER_PORT) { [int]$env:SYSML_VIEWER_PORT } else { 8797 }
}

$logDir = Join-Path $Root 'data\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'worker.log'

function Write-Log([string]$Message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Resolve-Python([string]$RepoRoot) {
    $candidates = @(
        (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
        (Join-Path $RepoRoot 'venv\Scripts\python.exe')
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python not found. Run: cd `"$RepoRoot`"; python -m venv .venv; .\.venv\Scripts\pip install -e ."
}

function Test-PortListening([int]$ListenPort) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::1', '::') } |
            Select-Object -First 1
        return [bool]$conn
    } catch {
        return $false
    }
}

function Test-WorkerHealth([string]$HealthUrl) {
    try {
        $h = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 4
        return ($h.status -eq 'ok' -or $h.status -eq 'degraded')
    } catch {
        return $false
    }
}

function Stop-ExistingWorker([string]$RepoRoot, [int]$ListenPort) {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            ($_.CommandLine -match [regex]::Escape($RepoRoot)) -and
            ($_.CommandLine -match 'sysml_spec_qa\.(viewer_app|__main__)' -or $_.CommandLine -match 'sysml_spec_qa serve')
        } |
        ForEach-Object {
            Write-Log "Stopping stale worker pid=$($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    if (Test-PortListening $ListenPort) {
        Write-Log "Port $ListenPort still in use (another app?) - worker will retry"
    }
}

$python = Resolve-Python $Root
$env:SYSML_SPEC_ROOT = $Root
$env:SYSML_VIEWER_HOST = $HostBind
$env:SYSML_VIEWER_PORT = "$Port"
$env:SYSML_VIEWER_URL = "http://127.0.0.1:$Port"
$healthLocal = "http://127.0.0.1:$Port/api/health"

$dbPath = Join-Path $Root 'data\index\spec.sqlite'
if (-not (Test-Path $dbPath)) {
    Write-Log "WARNING index missing at $dbPath - run: python -m sysml_spec_qa ingest --version 2.0"
}

if ((Test-PortListening $Port) -and (Test-WorkerHealth $healthLocal)) {
    Write-Log "Already running on port $Port (health ok)"
    exit 0
}

Stop-ExistingWorker -RepoRoot $Root -ListenPort $Port
Write-Log "SysML spec worker root=$Root python=$python port=$Port"

while ($true) {
    if (Test-PortListening $Port) {
        Write-Log "Port $Port already listening - holding (another worker?)"
        Start-Sleep -Seconds 30
        continue
    }

    Write-Log "Starting viewer on http://127.0.0.1:$Port (bind $HostBind)"
    $proc = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'sysml_spec_qa', 'serve') `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'serve.out.log') `
        -RedirectStandardError (Join-Path $logDir 'serve.err.log') `
        -PassThru

    Wait-Process -Id $proc.Id
    $code = $proc.ExitCode
    Write-Log "Viewer exited code=$code - restart in ${RestartSeconds}s"
    Start-Sleep -Seconds $RestartSeconds
}
