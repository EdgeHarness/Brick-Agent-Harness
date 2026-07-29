$ErrorActionPreference = "Stop"

if ($env:PYTHON) {
    $python = $env:PYTHON
    $pythonArgs = @()
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
    $pythonArgs = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
    $pythonArgs = @("-3")
} else {
    throw "No Python 3 interpreter found. Install Python or set PYTHON."
}

& $python @pythonArgs (Join-Path $PSScriptRoot "run_agent.py") @args
exit $LASTEXITCODE
