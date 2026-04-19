#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV="$BACKEND_DIR/.venv"

CLEAN=false
for arg in "$@"; do
  [[ "$arg" == "--clean" ]] && CLEAN=true
done

echo "=== GenreGrid build ==="

if $CLEAN; then
  echo ""
  echo "[ clean ] Removing previous build artefacts..."
  rm -rf "$BACKEND_DIR/dist" "$BACKEND_DIR/build" "$FRONTEND_DIR/release"
  echo "  Done."
fi

# ── Backend ──────────────────────────────────────────────────────────────────

echo ""
echo "[ 1/4 ] Building backend..."

if [ ! -d "$VENV" ]; then
  echo "  Creating Python venv..."
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "  Installing Python dependencies..."
pip install -q -r "$BACKEND_DIR/requirements.txt"
pip install -q pyinstaller

echo "  Freezing requirements-lock.txt..."
pip freeze > "$BACKEND_DIR/requirements-lock.txt"

echo "  Running PyInstaller..."
cd "$BACKEND_DIR"
pyinstaller genregrid.spec --distpath dist --workpath build/pyinstaller --noconfirm

deactivate

echo "  Backend built → backend/dist/genregrid-backend"

# ── Frontend ─────────────────────────────────────────────────────────────────

echo ""
echo "[ 2/4 ] Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm install --silent

echo ""
echo "[ 3/4 ] Type-checking frontend..."
npx vue-tsc --noEmit

echo ""
echo "[ 4/4 ] Building frontend + packaging..."
npm run build:electron

echo ""
echo "=== Done! Packages are in frontend/release/ ==="
