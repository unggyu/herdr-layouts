$ErrorActionPreference = 'Stop'
if (Test-Path (Join-Path $PSScriptRoot 'data\PAUSED')) { exit 0 }
$python = '__HERDR_PYTHONW_PS__'
$service = Join-Path $PSScriptRoot 'service.py'
Start-Process -FilePath $python -ArgumentList @('-I', ('"' + $service + '"'), '--watch') -WindowStyle Hidden
