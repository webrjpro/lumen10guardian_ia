$ErrorActionPreference = 'Stop'
$guardianRoot = Split-Path $PSScriptRoot -Parent
$script = Join-Path $PSScriptRoot 'Iniciar-Guardian.ps1'
$taskAction = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument "-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File `"$script`"" -WorkingDirectory $guardianRoot
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName 'Lumen10 Guardian Local' -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description 'Guardian local supervisionado; nao publica em producao sem adaptador habilitado.' -Force | Out-Null
    Write-Host 'Inicializacao automatica registrada no logon deste usuario.'
} catch {
    # Fallback por usuário sem solicitar elevação. VBScript mantém janela oculta.
    $startup = [Environment]::GetFolderPath('Startup')
    $launcher = Join-Path $startup 'Lumen10Guardian.vbs'
    $command = 'pwsh.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "' + $script + '"'
    $content = 'CreateObject("WScript.Shell").Run "' + $command.Replace('"','""') + '", 0, False'
    Set-Content -LiteralPath $launcher -Value $content -Encoding ASCII
    Write-Host 'Inicializacao registrada na pasta Startup deste usuario.'
}
