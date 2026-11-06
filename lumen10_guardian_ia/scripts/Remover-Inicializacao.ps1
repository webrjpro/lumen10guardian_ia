$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName 'Lumen10 Guardian Local' -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName 'Lumen10 Guardian Local' -Confirm:$false }
$launcher = Join-Path ([Environment]::GetFolderPath('Startup')) 'Lumen10Guardian.vbs'
if (Test-Path -LiteralPath $launcher) { Remove-Item -LiteralPath $launcher }
Write-Host 'Inicializacao automatica removida. Dados e credenciais locais preservados.'
