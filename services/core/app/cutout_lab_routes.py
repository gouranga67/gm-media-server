"""Private, read-only access to explicitly generated prototype comparisons."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import connection
from app.cutout_lab import artifact_path

router = APIRouter(prefix="/api/v1", tags=["cutout lab"])


@router.get("/jobs/{job_id}/cutout-lab/{key}/{filename}")
def get_cutout_artifact(job_id: UUID, key: str,
    filename: Literal["comparison.mp4", "contact.png", "matte.png", "report.json"]):
    with connection() as database:
        job = database.execute("SELECT id FROM jobs WHERE id=%s", (job_id,)).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        path, media_type = artifact_path(get_settings().media_root, job_id, key, filename)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=404, detail="cutout comparison is unavailable or changed")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})
