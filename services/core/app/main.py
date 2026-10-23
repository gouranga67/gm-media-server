from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from redis import Redis

from app.config import get_settings
from app.editing import router as editing_router
from app.projects import router as projects_router
from app.upload_hooks import router as upload_hooks_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="GM Media API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(projects_router)
app.include_router(editing_router)
app.include_router(upload_hooks_router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"service": "api", "status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["postgres"] = "ok"
    except Exception as error:
        raise HTTPException(status_code=503, detail="postgres unavailable") from error

    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        client.close()
        checks["redis"] = "ok"
    except Exception as error:
        raise HTTPException(status_code=503, detail="redis unavailable") from error

    return {"service": "api", "status": "ready", "checks": checks}


@app.get("/api/v1/system")
def system_information() -> dict[str, Any]:
    settings = get_settings()
    return {
        "service": "gm-media-api",
        "version": app.version,
        "environment": settings.app_env,
        "content_policy": {
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }
