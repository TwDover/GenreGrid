from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_styles import router as styles_router
from app.api.routes_generate import router as generate_router
from app.services.cleanup import cleanup_old_exports


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_old_exports()
    yield


app = FastAPI(title="GenreGrid API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(styles_router)
app.include_router(generate_router)
