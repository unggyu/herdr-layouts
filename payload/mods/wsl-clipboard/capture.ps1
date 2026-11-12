param([int]$TerminalProcessId = 0)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if (-not [System.Windows.Forms.Clipboard]::ContainsImage()) {
    @{kind='text'} | ConvertTo-Json -Compress
    exit 0
}
$usesWsl = $false
if ($TerminalProcessId -gt 0) {
    $processes = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name)
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $pending.Enqueue($TerminalProcessId)
    while ($pending.Count -gt 0) {
        $current = $pending.Dequeue()
        if (-not $seen.Add($current)) { continue }
        foreach ($proc in $processes) {
            if ($proc.ProcessId -eq $current -and $proc.Name -ieq 'wsl.exe') { $usesWsl = $true }
            if ($proc.ParentProcessId -eq $current) { $pending.Enqueue([int]$proc.ProcessId) }
        }
    }
}
$dir = Join-Path $env:LOCALAPPDATA 'Temp\herdr-clipboard'
New-Item -ItemType Directory -Force $dir | Out-Null
$path = Join-Path $dir ('image-' + [guid]::NewGuid().ToString('N') + '.png')
$image = [System.Windows.Forms.Clipboard]::GetImage()
try { $image.Save($path, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $image.Dispose() }
$inputPath = $path
if ($usesWsl) {
    $drive = $path.Substring(0,1).ToLowerInvariant()
    $inputPath = '/mnt/' + $drive + '/' + $path.Substring(3).Replace('\','/')
}
@{kind='image';path=$inputPath;windowsPath=$path;wsl=$usesWsl} | ConvertTo-Json -Compress
