# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Point the app's writable data dir at a throwaway directory for the run.

In a source checkout `DATA_DIR` is the repo, so every test that round-trips
`/generate` wrote its exports into `backend/exports/` and — whenever the result
came out all-green — a keeper into `backend/library/`. That library is not inert
storage: `build_scoring_style` blends its rhythm patterns into the quality
scorer's reference, so running the suite quietly moved future generation scores
and invalidated `docs/quality-baseline-v3.json`.

This must run before anything imports `app.core.config`, which reads the
environment once at import time — hence a module-level assignment in conftest
(pytest imports conftest before collecting test modules) rather than a fixture.
"""
import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="genregrid-tests-")
os.environ.setdefault("GENREGRID_DATA_DIR", _TMP_DATA_DIR)
