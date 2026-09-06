param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
