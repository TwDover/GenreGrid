"""
Entry point for the packaged Electron app.
Spawned by the Electron main process with the port as the first argument.
"""
import multiprocessing
import sys

import uvicorn


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    # Required on Windows when using PyInstaller --onedir
    multiprocessing.freeze_support()
    main()
