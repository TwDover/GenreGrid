# GenreGrid — run the app in your browser (Windows; mirror of start.sh).
# Usage: .\start.ps1 [-Rebuild]
# Builds the frontend once (reused on later runs; pass -Rebuild after pulling
# changes), starts the backend (:8000) and a static server (:4173), and opens
# your browser. Ctrl+C stops everything. For development with hot reload use
# .\dev.ps1 instead.
param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$AppUrl = "http://localhost:4173"

# Use whichever venv already exists (.venv preferred, venv accepted), else create .venv
if (Test-Path (Join-Path $BackendDir ".venv")) {
    $Venv = Join-Path $BackendDir ".venv"
} elseif (Test-Path (Join-Path $BackendDir "venv")) {
    $Venv = Join-Path $BackendDir "venv"
} else {
    $Venv = Join-Path $BackendDir ".venv"
    Write-Host "[ start ] Creating Python venv..."
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "[ start ] Syncing Python dependencies..."
& $Python -m pip install -q -r (Join-Path $BackendDir "requirements.txt")

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[ start ] Installing frontend dependencies..."
    Push-Location $FrontendDir
    try { npm install --silent } finally { Pop-Location }
}

if ($Rebuild -or -not (Test-Path (Join-Path $FrontendDir "dist"))) {
    Write-Host "[ start ] Building frontend (one-time; pass -Rebuild to refresh)..."
    Push-Location $FrontendDir
    try {
        npx vite build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    } finally { Pop-Location }
} else {
    Write-Host "[ start ] Reusing existing frontend build (pass -Rebuild to refresh)."
}

Write-Host "[ start ] Starting backend on http://localhost:8000 ..."
$env:CORS_ORIGINS = "http://localhost:4173,http://127.0.0.1:4173"
$Backend = Start-Process -FilePath $Python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" `
    -WorkingDirectory $BackendDir -NoNewWindow -PassThru

try {
    # Open the browser shortly after the static server comes up
    Start-Job -ScriptBlock {
        param($url)
        Start-Sleep -Seconds 2
        Start-Process $url
    } -ArgumentList $AppUrl | Out-Null

    Write-Host "[ start ] Serving app at $AppUrl  (Ctrl+C to stop)"
    Push-Location $FrontendDir
    try { npx vite preview --port 4173 --strictPort } finally { Pop-Location }
} finally {
    Write-Host ""
    Write-Host "[ start ] Stopping backend..."
    try { taskkill /PID $Backend.Id /T /F 2>$null | Out-Null } catch {}
    Remove-Item Env:\CORS_ORIGINS -ErrorAction SilentlyContinue
}
