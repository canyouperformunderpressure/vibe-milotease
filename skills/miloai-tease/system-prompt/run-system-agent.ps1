# Launch a supported agent with an explicitly user-supplied system prompt.

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir 'run_system_agent.py'
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $Python) {
    Write-Error 'Python not found on PATH; the Milo editor tools require it as well.'
    exit 1
}

& $Python.Source $PythonScript @args
exit $LASTEXITCODE
