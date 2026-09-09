<#
.SYNOPSIS
  Register SysmlSpecQa-Worker (logon + boot) like quatermaster-backup.

.EXAMPLE
  .\scripts\install-worker.ps1
  Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File C:\workspace\sysml-spec-qa\scripts\install-worker.ps1'
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [int]$Port = 0,
    [string]$TaskName = 'SysmlSpecQa-Worker',
    [string]$ShortcutName = 'SysmlSpecQa-Worker.lnk'
)

$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { 'C:\workspace\sysml-spec-qa' }
}
$Root = (Resolve-Path $Root).Path
$worker = Join-Path $Root 'scripts\worker.ps1'
if (-not (Test-Path $worker)) { throw "Missing $worker" }

if ($Port -le 0) {
    $Port = if ($env:SYSML_VIEWER_PORT) { [int]$env:SYSML_VIEWER_PORT } else { 8797 }
}

$userId = if ($env:USERDOMAIN -and $env:USERNAME) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$workerArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$worker`" -Root `"$Root`" -Port $Port -HostBind 0.0.0.0"

function Register-WorkerTask {
    param([string]$Name, [string]$Argument, $Triggers)
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    cmd /c "schtasks /Delete /TN `"$Name`" /F >nul 2>&1" | Out-Null
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Argument
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
    try {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Triggers -Settings $settings -Principal $principal -Force | Out-Null
        Write-Host "Task registered: $Name" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "Task skipped ($Name): $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

$boot = New-ScheduledTaskTrigger -AtStartup
$boot.Delay = 'PT45S'
$logon = New-ScheduledTaskTrigger -AtLogOn
$taskOk = Register-WorkerTask -Name $TaskName -Argument $workerArgs -Triggers @($boot, $logon)

if (-not $taskOk) {
    $tr = "powershell.exe $workerArgs"
    cmd /c "schtasks /Create /TN `"$TaskName`" /TR `"$tr`" /SC ONLOGON /F /RL LIMITED" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Task registered via schtasks (AtLogOn): $TaskName" -ForegroundColor Green
        $taskOk = $true
    } else {
        Write-Host "Could not register scheduled task (Startup shortcut still installed)." -ForegroundColor Yellow
    }
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).
    IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    netsh advfirewall firewall delete rule name="SysmlSpecQa-$Port" | Out-Null
    netsh advfirewall firewall add rule name="SysmlSpecQa-$Port" dir=in action=allow protocol=TCP localport=$Port profile=any | Out-Null
    Write-Host "Firewall rule added for port $Port" -ForegroundColor Green
} else {
    Write-Host "Not elevated - skip firewall (Tailscale/LAN probe may fail until re-run as admin)" -ForegroundColor Yellow
}

$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup $ShortcutName
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcutPath)
$sc.TargetPath = 'powershell.exe'
$sc.Arguments = $workerArgs
$sc.WorkingDirectory = $Root
$sc.WindowStyle = 7
$sc.Description = 'SysML v2 spec QA viewer worker (Cursor MCP links)'
$sc.Save()
Write-Host "Startup shortcut: $shortcutPath" -ForegroundColor Green

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'sysml-spec-qa\\scripts\\worker\.ps1' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Process -FilePath 'powershell.exe' -ArgumentList $workerArgs -WindowStyle Hidden
Start-Sleep -Seconds 4

$healthUrl = "http://127.0.0.1:$Port/api/health"
try {
    $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 8
    Write-Host ("Worker health: {0}" -f $h.status) -ForegroundColor Green
} catch {
    Write-Host ("Worker started but health probe failed: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
    Write-Host "  Check data\logs\worker.log and serve.err.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Viewer: http://127.0.0.1:$Port (local) | http://quatermaster:$Port (LAN/Tailscale)" -ForegroundColor Cyan
Write-Host "Health: $healthUrl" -ForegroundColor Cyan
Write-Host "Logs:   $Root\data\logs\" -ForegroundColor Cyan
if ($taskOk) { Write-Host "Task:   $TaskName (AtStartup+45s, AtLogOn)" -ForegroundColor Cyan }
Write-Host ""
Write-Host "Set SYSML_VIEWER_URL=http://127.0.0.1:$Port in Cursor MCP config." -ForegroundColor DarkGray
