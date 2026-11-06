param([switch]$Autostart, [switch]$Extensao)
$ErrorActionPreference = 'Stop'
$guardianRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $guardianRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { & python -m venv (Join-Path $guardianRoot '.venv'); if ($LASTEXITCODE) { throw 'Falha ao criar venv' } }
$constraints = Join-Path $guardianRoot 'requirements-runtime.lock'
if (Test-Path -LiteralPath $constraints) { & $python -m pip install -c $constraints -e $guardianRoot } else { & $python -m pip install -e $guardianRoot }
if ($LASTEXITCODE) { throw 'Falha ao instalar dependencias' }
& $python -m guardian doctor
& $python -m guardian connect --path (Split-Path $guardianRoot -Parent)
if ($LASTEXITCODE) { throw 'Falha ao registrar pasta do projeto' }
if ($Autostart) { & (Join-Path $PSScriptRoot 'Instalar-Inicializacao.ps1') }
if ($Extensao) { & (Join-Path $PSScriptRoot 'Instalar-Extensao.ps1') }
Write-Host 'Instalado. Execute Abrir-Painel.ps1 e clique Ativar Guardian.' -ForegroundColor Green
