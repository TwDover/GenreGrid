# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_styles import router as styles_router
from app.api.routes_generate import router as generate_router
from app.api.routes_song import router as song_router
from app.api.routes_library import router as library_router
from app.services.cleanup import cleanup_old_exports


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_old_exports()
    yield


app = FastAPI(title="GenreGrid API", version="0.1.0", lifespan=lifespan)

# A packaged renderer runs on a random 127.0.0.1:<port>, so we can't pin a fixed
# origin — but the API must NOT be open to arbitrary websites (a page the user
# visits in their browser could otherwise POST to the local backend). Allow any
# localhost / 127.0.0.1 origin (any port) via regex: same-machine requests keep
# working, while a browser blocks evil.com's cross-origin JSON POSTs at preflight.
# `CORS_ORIGINS="*"` (the old packaged setting) now maps to this safe localhost
# regex rather than a literal wildcard; an explicit comma-list is still honored.
_LOCALHOST_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()

if _cors_env and _cors_env != "*":
    _cors_kwargs = {"allow_origins": [o.strip() for o in _cors_env.split(",") if o.strip()]}
else:
    _cors_kwargs = {"allow_origin_regex": _LOCALHOST_ORIGIN_RE}

app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
    **_cors_kwargs,
)

app.include_router(health_router)
app.include_router(styles_router)
app.include_router(generate_router)
app.include_router(song_router)
app.include_router(library_router)
