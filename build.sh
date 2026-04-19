#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV="$BACKEND_DIR/.venv"

echo "=== GenreGrid build ==="

# ── Backend ──────────────────────────────────────────────────────────────────

echo ""
echo "[ 1/3 ] Building backend..."

if [ ! -d "$VENV" ]; then
  echo "  Creating Python venv..."
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "  Installing Python dependencies..."
pip install -q -r "$BACKEND_DIR/requirements.txt"
pip install -q pyinstaller

echo "  Running PyInstaller..."
cd "$BACKEND_DIR"
pyinstaller genregrid.spec --distpath dist --workpath build/pyinstaller --noconfirm

deactivate

echo "  Backend built → backend/dist/genregrid-backend"

# ── Frontend ─────────────────────────────────────────────────────────────────

echo ""
echo "[ 2/3 ] Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm install --silent

echo ""
echo "[ 3/3 ] Building frontend + packaging..."
npm run build:electron

echo ""
echo "=== Done! Packages are in frontend/release/ ==="
