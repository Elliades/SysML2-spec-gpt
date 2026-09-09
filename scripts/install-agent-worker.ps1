<#
.SYNOPSIS
  Register this repo with the Cursor Cloud Agent worker (My Machines).

.DESCRIPTION
  Adds sysml-spec-qa to homelab/start-cursor-agent-worker.ps1 and starts
  `agent worker ... start` as Quatermaster-sysml-spec-qa.

  This is NOT the MCP server and NOT the local viewer (port 8797).
  See scripts/install-viewer-worker.ps1 for the spec viewer autostart.

.EXAMPLE
  .\scripts\install-agent-worker.ps1
#>
[CmdletBinding()]
param(
    [string]$HomelabScript = 'C:\Users\Quatermaster\homelab\start-cursor-agent-worker.ps1',
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    $RepoRoot = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { 'C:\workspace\sysml-spec-qa' }
}
$RepoRoot = (Resolve-Path $RepoRoot).Path
$slug = 'sysml-spec-qa'
$entry = "@{ Slug = '$slug'; Path = '$RepoRoot' }"

if (-not (Test-Path $HomelabScript)) {
    throw "Missing homelab worker script: $HomelabScript`nRun: irm 'https://cursor.com/install?win32=true' | iex`nThen create homelab/start-cursor-agent-worker.ps1"
}

$content = Get-Content -Raw -Encoding UTF8 $HomelabScript
if ($content -notmatch [regex]::Escape($RepoRoot)) {
    $content = $content -replace '(\s*\@\{ Slug = ''risu-ai''[^\}]+\}\s*\r?\n)(\))', "`$1    $entry`r`n`$2"
    Set-Content -Path $HomelabScript -Value $content -Encoding UTF8 -NoNewline
    Write-Host "Added $slug to $HomelabScript" -ForegroundColor Green
} else {
    Write-Host "Already listed in $HomelabScript" -ForegroundColor DarkGray
}

$autostart = Join-Path $HomelabScript.Replace('start-cursor-agent-worker.ps1', 'install-cursor-agent-autostart.ps1')
if (Test-Path $autostart) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $autostart
} else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $HomelabScript
}

Write-Host ""
Write-Host "In Cursor: Agents -> environment -> My Machines -> Quatermaster-sysml-spec-qa" -ForegroundColor Cyan
Write-Host "Repo label: Elliades/SysML2-spec-gpt (git remote origin)" -ForegroundColor DarkGray
Write-Host "Slack/GitHub: worker=Quatermaster-sysml-spec-qa" -ForegroundColor DarkGray
