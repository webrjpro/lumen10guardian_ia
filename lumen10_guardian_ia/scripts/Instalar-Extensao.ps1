$ErrorActionPreference = 'Stop'
$guardianRoot = Split-Path $PSScriptRoot -Parent
$extension = Join-Path $guardianRoot 'vscode-extension'
Push-Location $extension
try {
    & npx.cmd --yes --package '@vscode/vsce' -- vsce package --allow-missing-repository --out 'guardian-0.1.0.vsix'
    if ($LASTEXITCODE) { throw 'Falha ao empacotar extensao' }
    & code --install-extension (Join-Path $extension 'guardian-0.1.0.vsix') --force
    if ($LASTEXITCODE) { throw 'Falha ao instalar extensao' }
} finally { Pop-Location }
Write-Host 'Extensao instalada. Abra Guardian: Abrir painel na paleta de comandos.'
