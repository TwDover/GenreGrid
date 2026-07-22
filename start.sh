#!/usr/bin/env bash
# GenreGrid — run the app in your browser (Linux / macOS).
# Usage: ./start.sh [--rebuild]
# Builds the frontend once (reused on later runs; pass --rebuild after pulling
# changes), starts the backend (:8000) and a static server (:4173), and opens
# your browser. Ctrl+C stops everything. For development with hot reload use
# ./dev.sh instead.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
APP_URL="http://localhost:4173"

REBUILD=false
for arg in "$@"; do
  [[ "$arg" == "--rebuild" ]] && REBUILD=true
done

# Use whichever venv already exists (.venv preferred, venv accepted), else create .venv
if [ -d "$BACKEND_DIR/.venv" ]; then
  VENV="$BACKEND_DIR/.venv"
elif [ -d "$BACKEND_DIR/venv" ]; then
  VENV="$BACKEND_DIR/venv"
else
  VENV="$BACKEND_DIR/.venv"
  echo "[ start ] Creating Python venv..."
  python3 -m venv "$VENV"
fi

echo "[ start ] Syncing Python dependencies..."
"$VENV/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[ start ] Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install --silent)
fi

if $REBUILD || [ ! -d "$FRONTEND_DIR/dist" ]; then
  echo "[ start ] Building frontend (one-time; pass --rebuild to refresh)..."
  (cd "$FRONTEND_DIR" && npx vite build)
else
  echo "[ start ] Reusing existing frontend build (pass --rebuild to refresh)."
fi

echo "[ start ] Starting backend on http://localhost:8000 ..."
(cd "$BACKEND_DIR" && CORS_ORIGINS="http://localhost:4173,http://127.0.0.1:4173" \
  "$VENV/bin/python" -m uvicorn app.main:app --port 8000) &
BACKEND_PID=$!

trap 'echo ""; echo "[ start ] Stopping backend..."; kill "$BACKEND_PID" 2>/dev/null || true' EXIT

# Open the browser once the static server is about to come up
if command -v xdg-open >/dev/null 2>&1; then
  (sleep 2 && xdg-open "$APP_URL") &
elif command -v open >/dev/null 2>&1; then
  (sleep 2 && open "$APP_URL") &
fi

echo "[ start ] Serving app at $APP_URL  (Ctrl+C to stop)"
cd "$FRONTEND_DIR"
npx vite preview --port 4173 --strictPort
