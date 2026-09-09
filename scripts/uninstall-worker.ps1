<#
.SYNOPSIS
  Remove SysmlSpecQa-Worker scheduled task and Startup shortcut.
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'SysmlSpecQa-Worker',
    [string]$ShortcutName = 'SysmlSpecQa-Worker.lnk'
)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
cmd /c "schtasks /Delete /TN `"$TaskName`" /F >nul 2>&1" | Out-Null

$startup = Join-Path ([Environment]::GetFolderPath('Startup')) $ShortcutName
if (Test-Path $startup) { Remove-Item $startup -Force }

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'sysml-spec-qa\\scripts\\worker\.ps1' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Removed $TaskName and $ShortcutName" -ForegroundColor Green
