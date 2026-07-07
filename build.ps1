# GenreGrid — one-command Windows build (mirror of build.sh).
# Usage:  .\build.ps1 [-Clean]
# Output: frontend\release\  (portable exe + NSIS installer)
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$Venv = Join-Path $BackendDir ".venv"

Write-Host "=== GenreGrid build ==="

if ($Clean) {
    Write-Host ""
    Write-Host "[ clean ] Removing previous build artefacts..."
    foreach ($p in @((Join-Path $BackendDir "dist"), (Join-Path $BackendDir "build"), (Join-Path $FrontendDir "release"))) {
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    Write-Host "  Done."
}

# -- Backend -------------------------------------------------------------------

Write-Host ""
Write-Host "[ 1/4 ] Building backend..."

if (-not (Test-Path $Venv)) {
    Write-Host "  Creating Python venv..."
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "  Installing Python dependencies..."
& $Python -m pip install -q -r (Join-Path $BackendDir "requirements.txt")
& $Python -m pip install -q pyinstaller

Write-Host "  Freezing requirements-lock.txt..."
& $Python -m pip freeze | Out-File -Encoding utf8 (Join-Path $BackendDir "requirements-lock.txt")

Write-Host "  Running PyInstaller..."
Push-Location $BackendDir
try {
    & $Python -m PyInstaller genregrid.spec --distpath dist --workpath build\pyinstaller --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Host "  Backend built -> backend\dist\genregrid-backend"

# -- Frontend ------------------------------------------------------------------

Write-Host ""
Write-Host "[ 2/4 ] Installing frontend dependencies..."
Push-Location $FrontendDir
try {
    npm install --silent
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Write-Host ""
    Write-Host "[ 3/4 ] Type-checking frontend..."
    npx vue-tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "Type-check failed" }

    Write-Host ""
    Write-Host "[ 4/4 ] Building frontend + packaging..."
    npm run build:electron
    if ($LASTEXITCODE -ne 0) { throw "Electron build failed" }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Done! Packages are in frontend\release\ ==="
