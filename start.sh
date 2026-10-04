#!/usr/bin/env bash
# Start QuoteDesk on http://127.0.0.1:8765 (macOS / Linux).
# First run creates .venv and installs dependencies; later runs start immediately.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "QuoteDesk needs Python 3.11 or newer (found: $("$PY" --version 2>&1 || echo none))." >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment…"
  "$PY" -m venv .venv
fi

# Reinstall only when requirements change.
REQ_HASH="$("$PY" -c 'import hashlib,sys; print(hashlib.sha1(open("backend/requirements.txt","rb").read()).hexdigest())')"
if [ "$(cat .venv/.requirements-hash 2>/dev/null || true)" != "$REQ_HASH" ]; then
  echo "Installing dependencies…"
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r backend/requirements.txt
  echo "$REQ_HASH" > .venv/.requirements-hash
fi

if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Building the interface…"
    (cd frontend && npm ci && npm run build)
  else
    echo "frontend/dist is missing and npm is not installed: the API will run, but there is no UI." >&2
  fi
fi

cd backend
# Migrations, seeding and the startup backup run inside the app on startup.
exec ../.venv/bin/python -m app --open "$@"
