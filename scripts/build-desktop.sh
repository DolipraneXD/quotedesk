#!/usr/bin/env bash
# Build the QuoteDesk desktop folder (dist/QuoteDesk) with PyInstaller.
# PyInstaller builds for the system it runs on: run this on Windows (build-desktop.bat) to get
# QuoteDesk.exe; CI does that on every tag (.github/workflows/desktop.yml).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
(cd frontend && npm ci && npm run build)
"$PY" -m pip install -q -r backend/requirements.txt "pyinstaller>=6.10"
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller \
  backend/packaging/quotedesk.spec
echo "Built dist/QuoteDesk. Copy the whole folder; start QuoteDesk inside it."
