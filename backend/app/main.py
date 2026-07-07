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

_cors_env = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(styles_router)
app.include_router(generate_router)
app.include_router(song_router)
app.include_router(library_router)
