"""
Entry point for the packaged Electron app.
Spawned by the Electron main process with the port as the first argument.
"""
import io
import multiprocessing
import sys

import uvicorn


def main() -> None:
    # The exe is built windowed (console=False) so no terminal appears behind
    # the app. When Electron spawns us it provides real stdio handles (piped to
    # backend.log); if the exe is launched directly there are none and
    # sys.stdout/stderr are None — give logging a sink so uvicorn doesn't crash.
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    # Required on Windows when using PyInstaller --onedir
    multiprocessing.freeze_support()
    main()
