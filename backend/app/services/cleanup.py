# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import shutil
import time

from app.core.config import EXPORTS_DIR, EXPORT_TTL_SECONDS


def cleanup_old_exports() -> int:
    """Delete export directories older than EXPORT_TTL_SECONDS. Returns count removed."""
    if not EXPORTS_DIR.exists():
        return 0

    now = time.time()
    removed = 0
    for entry in EXPORTS_DIR.iterdir():
        if entry.is_dir() and (now - entry.stat().st_mtime) > EXPORT_TTL_SECONDS:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed
