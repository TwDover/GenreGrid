#!/usr/bin/env bash
# GenreGrid — one-command build for Linux and macOS.
# Usage:  ./build.sh [--clean]
# Output: frontend/release/  (AppImage + .deb on Linux, .dmg + .zip on macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV="$BACKEND_DIR/.venv"

# macOS: skip code-signing discovery — builds are unsigned (see README).
if [[ "$(uname -s)" == "Darwin" ]]; then
  export CSC_IDENTITY_AUTO_DISCOVERY=false
fi

CLEAN=false
for arg in "$@"; do
  [[ "$arg" == "--clean" ]] && CLEAN=true
done

# ── Preflight: required build tools ───────────────────────────────────────────
# Fail early with an install hint instead of a cryptic error 20 lines into the
# build. Package names differ per distro; map them without bash-4 associative
# arrays so this stays macOS (bash 3.2) compatible.
_pkg_for() {  # $1 = command, $2 = manager
  case "$1:$2" in
    python3:pacman) echo python  ;;  node:pacman) echo nodejs ;;  npm:pacman) echo npm ;;
    python3:apt)    echo python3 ;;  node:apt)    echo nodejs ;;  npm:apt)    echo npm ;;
  esac
}

_missing=""
for _cmd in python3 node npm; do
  command -v "$_cmd" >/dev/null 2>&1 || _missing="$_missing $_cmd"
done

if [ -n "$_missing" ]; then
  echo "Error: missing required build tools:$_missing" >&2
  if command -v pacman >/dev/null 2>&1; then
    _pkgs=""; for _c in $_missing; do _pkgs="$_pkgs $(_pkg_for "$_c" pacman)"; done
    echo "  Arch / CachyOS:  sudo pacman -S --needed base-devel$_pkgs" >&2
  elif command -v apt-get >/dev/null 2>&1; then
    _pkgs=""; for _c in $_missing; do _pkgs="$_pkgs $(_pkg_for "$_c" apt)"; done
    echo "  Debian / Ubuntu: sudo apt-get install$_pkgs" >&2
  fi
  exit 1
fi

# UPX is optional: genregrid.spec compresses the backend with it when present,
# and PyInstaller silently skips it when absent — just a larger bundle.
if ! command -v upx >/dev/null 2>&1; then
  echo "Note: 'upx' not found — backend won't be compressed (fine, just larger)."
  command -v pacman >/dev/null 2>&1 && echo "      For smaller builds: sudo pacman -S upx"
fi

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
