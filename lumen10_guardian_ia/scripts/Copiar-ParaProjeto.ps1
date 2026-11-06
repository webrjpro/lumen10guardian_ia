param([Parameter(Mandatory=$true)][string]$ProjectPath)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) { throw 'A pasta do projeto precisa existir.' }
$project = (Resolve-Path -LiteralPath $ProjectPath).Path
$target = [IO.Path]::GetFullPath((Join-Path $project 'lumen10_guardian_ia'))
if ($target -eq $source -or $target.StartsWith($source + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destino precisa estar fora da instalacao atual.' }
if (Test-Path -LiteralPath $target) { throw 'A pasta Guardian ja existe no destino. Atualize com backup e revisao.' }
New-Item -ItemType Directory -Path $target | Out-Null
foreach ($name in @('guardian','agents','scripts','vscode-extension','docs','tests')) {
    $origin = Join-Path $source $name
    Get-ChildItem -LiteralPath $origin -Recurse -File | Where-Object {
        $_.FullName -notmatch '[\\/](node_modules|__pycache__|\.pytest_cache|\.ruff_cache)[\\/]' -and $_.Extension -ne '.vsix'
    } | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($source, $_.FullName)
        $destination = Join-Path $target $relative
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination
    }
}
foreach ($name in @('pyproject.toml','README.md','LICENSE.md','requirements-runtime.lock','requirements-dev.lock','.gitignore')) {
    $origin = Join-Path $source $name
    if (Test-Path -LiteralPath $origin) { Copy-Item -LiteralPath $origin -Destination (Join-Path $target $name) }
}
Write-Host "Guardian copiado para $target. Execute scripts/Instalar-Guardian.ps1 nessa pasta."
