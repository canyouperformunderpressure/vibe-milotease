# MiloAI NSFW module installer — PowerShell entry point.
# Detection and installation live in init_system_prompt.py so this entry point
# and the Bash entry point have identical behavior.

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
