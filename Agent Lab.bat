@echo off
rem Double-click this file (Windows) to open the Agent Lab in your browser.
cd /d "%~dp0"

set "PY="
set "PY_ARGS="
if defined PYTHON (
  set "PY=%PYTHON%"
  goto python_found
)
where python 1>nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  goto python_found
)
where py 1>nul 2>nul
if not errorlevel 1 (
  set "PY=py"
  set "PY_ARGS=-3"
  goto python_found
)
echo No Python 3 interpreter found. Install Python or set the PYTHON environment variable.
exit /b 1

:python_found
"%PY%" %PY_ARGS% -c "import requests, pptx, openpyxl" 1>nul 2>nul
if errorlevel 1 (
  echo Installing the agent's Python packages ^(one time^)...
  "%PY%" %PY_ARGS% -m pip install --quiet -r requirements-lock.txt
  if errorlevel 1 exit /b 1
)

"%PY%" %PY_ARGS% -m webui.server
pause
