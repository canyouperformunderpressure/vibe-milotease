# User-supplied system prompt installer — PowerShell entry point.
# This project does not bundle a default prompt; all arguments are forwarded
# to init_system_prompt.py, including the required --source file.

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir 'init_system_prompt.py'
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $Python) {
    Write-Error 'Python not found on PATH; the Milo editor tools require it as well.'
    exit 1
}

& $Python.Source $PythonScript @args
exit $LASTEXITCODE
