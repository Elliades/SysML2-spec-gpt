<#
.SYNOPSIS
  Register sysml-spec MCP in Cursor (global + optional project merge).

.EXAMPLE
  .\scripts\install-cursor-mcp.ps1
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$Port = '8797',
    [switch]$SkipGlobal,
    [switch]$SkipQHome
)

$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { 'C:\workspace\sysml-spec-qa' }
}
$Root = (Resolve-Path $Root).Path

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$entry = @{
    command = ($python -replace '\\', '/')
    args    = @('-m', 'sysml_spec_qa.mcp_server')
    env     = @{
        SYSML_SPEC_ROOT  = ($Root -replace '\\', '/')
        SYSML_VIEWER_URL = "http://127.0.0.1:$Port"
    }
}

function Merge-McpJson([string]$Path) {
    $servers = @{}
    if (Test-Path $Path) {
        try {
            $existing = Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
            if ($existing.mcpServers) {
                $existing.mcpServers.PSObject.Properties | ForEach-Object {
                    $servers[$_.Name] = $_.Value
                }
            }
        } catch {
            Write-Host "Warning: could not parse $Path, recreating" -ForegroundColor Yellow
        }
    }
    $servers['sysml-spec'] = [pscustomobject]$entry
    $doc = [pscustomobject]@{ mcpServers = [pscustomobject]$servers }
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    ($doc | ConvertTo-Json -Depth 8) + "`n" | Set-Content -Path $Path -Encoding UTF8
    Write-Host "Updated: $Path" -ForegroundColor Green
}

if (-not $SkipGlobal) {
    Merge-McpJson (Join-Path $env:USERPROFILE '.cursor\mcp.json')
}

Copy-Item (Join-Path $Root '.cursor\mcp.json') (Join-Path $Root '.cursor\mcp.json.example') -Force -ErrorAction SilentlyContinue
Merge-McpJson (Join-Path $Root '.cursor\mcp.json')

$qhome = 'C:\workspace\Q-Home\.cursor\mcp.json'
if (-not $SkipQHome -and (Test-Path (Split-Path $qhome -Parent))) {
    Merge-McpJson $qhome
}

Write-Host ""
Write-Host "Restart Cursor, then open Settings > MCP (or Features > MCP)." -ForegroundColor Cyan
Write-Host "You should see: sysml-spec (tools: spec_answer_pack, spec_element, ...)" -ForegroundColor Cyan
Write-Host "Viewer must be running: http://127.0.0.1:$Port" -ForegroundColor DarkGray
