#!/usr/bin/env bash
# GenreGrid — one-command dev servers for Linux and macOS.
# Usage: ./dev.sh
# Starts the FastAPI backend (:8000, auto-reload) and the Vite frontend (:5173)
# together; Ctrl+C stops both. First run creates the venv / installs deps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

# Use whichever venv already exists (.venv preferred, venv accepted), else create .venv
if [ -d "$BACKEND_DIR/.venv" ]; then
  VENV="$BACKEND_DIR/.venv"
elif [ -d "$BACKEND_DIR/venv" ]; then
  VENV="$BACKEND_DIR/venv"
else
  VENV="$BACKEND_DIR/.venv"
  echo "[ dev ] Creating Python venv..."
  python3 -m venv "$VENV"
fi

echo "[ dev ] Syncing Python dependencies..."
"$VENV/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[ dev ] Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install --silent)
fi

echo "[ dev ] Starting backend on http://localhost:8000 ..."
(cd "$BACKEND_DIR" && "$VENV/bin/python" -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

# Stop the backend when this script exits (Ctrl+C, vite quitting, errors)
trap 'echo ""; echo "[ dev ] Stopping backend..."; kill "$BACKEND_PID" 2>/dev/null || true' EXIT

echo "[ dev ] Starting frontend on http://localhost:5173 ..."
cd "$FRONTEND_DIR"
npm run dev
