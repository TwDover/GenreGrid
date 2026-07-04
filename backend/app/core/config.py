# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STYLES_DIR = BASE_DIR / "app" / "styles"

# When packaged with PyInstaller, use a writable user-data directory for
# generated files so they survive outside the read-only bundle extraction dir.
if getattr(sys, "frozen", False):
    _env_override = os.environ.get("GENREGRID_DATA_DIR")
    if _env_override:
        DATA_DIR = Path(_env_override)
    elif sys.platform == "win32":
        DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GenreGrid"
    else:
        DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "GenreGrid"
else:
    DATA_DIR = BASE_DIR

EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

CUSTOM_STYLES_DIR = DATA_DIR / "custom_styles"
CUSTOM_STYLES_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_TTL_SECONDS = int(os.environ.get("EXPORT_TTL_SECONDS", "3600"))
