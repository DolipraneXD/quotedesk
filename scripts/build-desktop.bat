@echo off
rem Build the QuoteDesk desktop folder (dist\QuoteDesk) with PyInstaller on Windows.
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe py -3 -m venv .venv || goto :error
pushd frontend
call npm ci || goto :error
call npm run build || goto :error
popd
.venv\Scripts\python -m pip install -q -r backend\requirements.txt "pyinstaller>=6.10" || goto :error
.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller backend\packaging\quotedesk.spec || goto :error
echo Built dist\QuoteDesk. Copy the whole folder; start QuoteDesk.exe inside it.
exit /b 0
:error
echo Build failed.
exit /b 1
