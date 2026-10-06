@echo off
rem Start QuoteDesk on http://127.0.0.1:8765 (Windows).
rem First run creates .venv and installs dependencies; later runs start immediately.
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 (
  echo QuoteDesk needs Python 3.11 or newer. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :error
)

rem Reinstall only when requirements change (compared with the copy saved at install time).
fc /b "backend\requirements.txt" ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :error
  copy /y "backend\requirements.txt" ".venv\requirements.installed" >nul
)

if not exist "frontend\dist\index.html" (
  where npm >nul 2>nul && (
    echo Building the interface...
    pushd frontend
    call npm ci || goto :error
    call npm run build || goto :error
    popd
  ) || echo frontend\dist is missing and npm is not installed: the API will run, but there is no UI.
)

cd backend
rem Migrations, seeding and the startup backup run inside the app on startup.
"..\.venv\Scripts\python.exe" -m app --open %*
exit /b %errorlevel%

:error
echo Startup failed. See the messages above.
pause
exit /b 1
