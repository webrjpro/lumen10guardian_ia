param([switch]$Foreground)
$ErrorActionPreference = 'Stop'
$guardianRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $guardianRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Execute Instalar-Guardian.ps1 primeiro.' }
if ($Foreground) { & $python -m guardian serve; exit $LASTEXITCODE }
$guardianPort = if ($env:GUARDIAN_PORT) { [int]$env:GUARDIAN_PORT } else { 8765 }
$health = $null
try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$guardianPort/healthz" -TimeoutSec 2 } catch { }
if ($health -and $health.service -eq 'lumen10-guardian') { return }
if ($health) { throw 'A porta configurada pertence a outro servico' }
Start-Process -FilePath $python -ArgumentList @('-m', 'guardian', 'supervise') -WorkingDirectory $guardianRoot -WindowStyle Hidden
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$guardianPort/healthz" -TimeoutSec 1
        if ($health.service -eq 'lumen10-guardian') { Write-Host "Guardian em http://127.0.0.1:$guardianPort"; return }
    } catch { }
}
throw 'Guardian nao iniciou. Verifique %LOCALAPPDATA%/Lumen10Guardian/service.log'
