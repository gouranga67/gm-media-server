from contextlib import asynccontextmanager
import json
import os
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from redis import Redis

from app.config import get_settings
from app.concepts import router as concepts_router
from app.creative_profiles import router as creative_profiles_router
from app.creative_assets import router as creative_assets_router
from app.brand_kits import router as brand_kits_router
from app.editing import router as editing_router
from app.library import router as library_router
from app.library_organization import router as library_organization_router
from app.learning import router as learning_router
from app.projects import router as projects_router
from app.productization import router as productization_router
from app.upload_hooks import router as upload_hooks_router
from app.runtime_metrics import performance_snapshot
from app.knowledge import router as knowledge_router


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

app.include_router(productization_router)
app.include_router(projects_router)
app.include_router(editing_router)
app.include_router(library_router)
app.include_router(library_organization_router)
app.include_router(knowledge_router)
app.include_router(concepts_router)
app.include_router(learning_router)
app.include_router(upload_hooks_router)
app.include_router(creative_profiles_router)
app.include_router(creative_assets_router)
app.include_router(brand_kits_router)


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
        "build_id": deployed_build_id(settings),
        "environment": settings.app_env,
        "content_policy": {
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }


def deployed_build_id(settings: Any) -> str:
    try:
        path = settings.appliance_status_path.parent / "build.json"
        if path.stat().st_size < 4096:
            return str(json.loads(path.read_text()).get("commit") or "unknown")[:64]
    except (OSError, ValueError):
        pass
    return os.environ.get("GM_BUILD_ID", "development")


@app.get("/api/v1/system/performance")
def system_performance() -> dict[str, Any]:
    try:
        return performance_snapshot(get_settings().media_root)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="runtime measurements are unavailable") from error


@app.get("/api/v1/system/health")
def appliance_health() -> dict[str, Any]:
    status_path = get_settings().appliance_status_path
    try:
        if status_path.stat().st_size > 65_536:
            raise ValueError("health snapshot is unexpectedly large")
        parsed = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("health snapshot must contain an object")
        return parsed
    except FileNotFoundError:
        return {
            "status": "pending",
            "alerts": ["appliance health snapshot has not been collected yet"],
            "generated_at": None,
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="appliance health snapshot is invalid") from error
