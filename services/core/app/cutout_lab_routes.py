"""Private access to bounded, non-destructive person-cutout comparisons."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.database import connection
from app.cutout_lab import artifact_path, create_comparison, select_sample
from app.editor_context import build_editor_context, resolve_internal_asset_source
from app.schemas import JobComposition

router = APIRouter(prefix="/api/v1", tags=["cutout lab"])


class CutoutComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edit_version: int = Field(strict=True, gt=0)


@router.post("/jobs/{job_id}/cutout-lab")
def create_cutout_preview(job_id: UUID, payload: CutoutComparisonRequest) -> dict:
    """Compare a short presenter sample against the chosen background; never alter the edit."""
    with connection() as database:
        job = database.execute(
            "SELECT id, composition FROM jobs WHERE id=%s", (job_id,)
        ).fetchone()
        row = database.execute(
            """SELECT r.version,r.status,p.document FROM edit_runs r
               LEFT JOIN edit_plans p ON p.id=r.edit_plan_id
               WHERE r.job_id=%s ORDER BY r.version DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    composition = JobComposition.model_validate(job.get("composition") or {})
    if composition.mode != "person_cutout":
        raise HTTPException(status_code=409, detail="choose Replace background — Beta when creating the job")
    if not row or row.get("version") != payload.edit_version:
        raise HTTPException(status_code=409, detail="this preview changed; refresh before testing background replacement")

    foreground_id = str(composition.foreground_asset_id)
    sample = None
    for clip_number, clip in enumerate((row.get("document") or {}).get("clips", []), start=1):
        if str(clip.get("asset_id") or "") != foreground_id:
            continue
        try:
            sample = select_sample(job_id, row, clip_number)
            break
        except ValueError:
            continue
    if sample is None:
        raise HTTPException(status_code=409, detail="the saved edit has no normal-speed presenter shot available for this test")

    try:
        context = build_editor_context(job_id, include_internal_paths=True)
        foreground = next(asset for asset in context["assets"] if str(asset["asset_id"]) == foreground_id)
        background = next(asset for asset in context["assets"]
            if str(asset["asset_id"]) == str(composition.background_asset_id))
        settings = get_settings()
        return create_comparison(
            resolve_internal_asset_source(settings, foreground), sample, settings,
            background_source=resolve_internal_asset_source(settings, background),
            background_asset_id=composition.background_asset_id,
        )
    except StopIteration:
        raise HTTPException(status_code=409, detail="the selected presenter or background is no longer attached")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=409, detail=str(error)[:240])


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
