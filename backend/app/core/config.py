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

# An explicit override always wins, frozen or not. In a source checkout DATA_DIR
# is the repo itself, so anything that writes a generation — including the test
# suite's /generate round-trips — lands in the real backend/library/, whose
# contents feed the quality scorer through build_scoring_style. Letting the tests
# point this at a tmp dir keeps a test run from silently moving scores (and with
# them docs/quality-baseline-v3.json). See backend/tests/conftest.py.
_env_override = os.environ.get("GENREGRID_DATA_DIR")

# When packaged with PyInstaller, use a writable user-data directory for
# generated files so they survive outside the read-only bundle extraction dir.
if _env_override:
    DATA_DIR = Path(_env_override)
elif getattr(sys, "frozen", False):
    if sys.platform == "win32":
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
