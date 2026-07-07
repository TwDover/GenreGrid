# GenreGrid — one-command dev servers for Windows (mirror of dev.sh).
# Usage: .\dev.ps1
# Starts the FastAPI backend (:8000, auto-reload) and the Vite frontend (:5173)
# together; Ctrl+C stops both. First run creates the venv / installs deps.
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

# Use whichever venv already exists (.venv preferred, venv accepted), else create .venv
if (Test-Path (Join-Path $BackendDir ".venv")) {
    $Venv = Join-Path $BackendDir ".venv"
} elseif (Test-Path (Join-Path $BackendDir "venv")) {
    $Venv = Join-Path $BackendDir "venv"
} else {
    $Venv = Join-Path $BackendDir ".venv"
    Write-Host "[ dev ] Creating Python venv..."
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "[ dev ] Syncing Python dependencies..."
& $Python -m pip install -q -r (Join-Path $BackendDir "requirements.txt")

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[ dev ] Installing frontend dependencies..."
    Push-Location $FrontendDir
    try { npm install --silent } finally { Pop-Location }
}

Write-Host "[ dev ] Starting backend on http://localhost:8000 ..."
$Backend = Start-Process -FilePath $Python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $BackendDir -NoNewWindow -PassThru

try {
    Write-Host "[ dev ] Starting frontend on http://localhost:5173 ..."
    Push-Location $FrontendDir
    try { npm run dev } finally { Pop-Location }
} finally {
    Write-Host ""
    Write-Host "[ dev ] Stopping backend..."
    # --reload spawns a child worker; stop the whole tree so :8000 is freed
    try { taskkill /PID $Backend.Id /T /F 2>$null | Out-Null } catch {}
}
