$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Iniciar-Guardian.ps1')
$guardianRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $guardianRoot '.venv/Scripts/python.exe') -m guardian open
