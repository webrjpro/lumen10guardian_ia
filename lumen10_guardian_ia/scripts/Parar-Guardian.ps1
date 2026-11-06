$guardianRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $guardianRoot '.venv/Scripts/python.exe') -m guardian stop
