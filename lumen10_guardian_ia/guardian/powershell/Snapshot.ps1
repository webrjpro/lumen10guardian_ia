$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$processes = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 6 Name, Id, @{Name='MemoryMB'; Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}
[ordered]@{
    capturedAt = [DateTimeOffset]::UtcNow.ToString('o')
    powershell = $PSVersionTable.PSVersion.ToString()
    operatingSystem = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    topProcesses = @($processes)
    drives = @(Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free)
} | ConvertTo-Json -Depth 5
