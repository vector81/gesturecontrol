$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Start-Process -FilePath $python -ArgumentList 'app.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'studio-output.log') -RedirectStandardError (Join-Path $PSScriptRoot 'studio-error.log')
