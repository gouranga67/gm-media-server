"""Private access to bounded, non-destructive person-cutout comparisons."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.database import connection
from app.cutout_lab import artifact_path, create_comparison, read_report, select_sample
from app.edit_plan import document_sha256
from app.editor_context import build_editor_context, resolve_internal_asset_source
from app.productization import assert_job_capacity
from app.schemas import JobComposition

router = APIRouter(prefix="/api/v1", tags=["cutout lab"])


class CutoutComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edit_version: int = Field(strict=True, gt=0)


class CutoutApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edit_version: int = Field(strict=True, gt=0)
    enabled: bool
    comparison_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


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


@router.post("/jobs/{job_id}/person-cutout", status_code=202)
def set_full_reel_cutout(job_id: UUID, payload: CutoutApplicationRequest) -> dict:
    """Queue a new local preview with or without the approved person matte."""
    settings = get_settings()
    with connection() as database:
        job = database.execute(
            "SELECT id, composition FROM jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        composition = JobComposition.model_validate(job.get("composition") or {})
        if composition.mode != "person_cutout":
            raise HTTPException(status_code=409, detail="this job was not created with Replace background")
        active = database.execute(
            "SELECT 1 FROM edit_runs WHERE job_id=%s AND status IN ('pending','planning','rendering') LIMIT 1",
            (job_id,),
        ).fetchone()
        if active:
            raise HTTPException(status_code=409, detail="wait for the current preview before changing background replacement")
        based_on = database.execute(
            """SELECT r.*,p.document FROM edit_runs r JOIN edit_plans p ON p.id=r.edit_plan_id
               WHERE r.job_id=%s AND r.version=%s AND r.status='ready'""",
            (job_id, payload.edit_version),
        ).fetchone()
        if not based_on:
            raise HTTPException(status_code=409, detail="refresh and use the latest ready preview")
        latest = database.execute(
            "SELECT max(version)::integer AS version FROM edit_runs WHERE job_id=%s", (job_id,)
        ).fetchone()
        if not latest or latest["version"] != payload.edit_version:
            raise HTTPException(status_code=409, detail="this preview changed; refresh before applying background replacement")
        if payload.enabled:
            if not payload.comparison_key:
                raise HTTPException(status_code=422, detail="run and accept the two-second comparison first")
            try:
                _, report = read_report(settings.media_root, job_id, payload.comparison_key)
            except (OSError, ValueError, KeyError, TypeError):
                raise HTTPException(status_code=409, detail="the accepted comparison is unavailable or no longer matches")
            sample = report["sample"]
            if (sample["edit_version"] != payload.edit_version
                or sample["plan_sha256"] != document_sha256(based_on["document"])
                or report.get("background_asset_id") != str(composition.background_asset_id)):
                raise HTTPException(status_code=409, detail="the accepted comparison belongs to a different edit or background")
        assert_job_capacity(database, job_id)
        document = composition.model_copy(update={"person_cutout_enabled": payload.enabled}).model_dump(mode="json")
        database.execute("UPDATE jobs SET composition=%s,status='previewing',updated_at=now() WHERE id=%s",
            (Jsonb(document), job_id))
        version = latest["version"] + 1
        row = database.execute(
            """INSERT INTO edit_runs(job_id,version,edit_plan_id,based_on_run_id,provider,model,
                   reasoning_effort,caption_corrections,locked_elements,duration_policy)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (job_id, version, based_on["edit_plan_id"], based_on["id"], based_on.get("provider"),
             based_on.get("model"), based_on.get("reasoning_effort"),
             Jsonb(based_on.get("caption_corrections") or []), Jsonb(based_on.get("locked_elements") or []),
             Jsonb(based_on["duration_policy"]) if based_on.get("duration_policy") else None),
        ).fetchone()
        database.execute(
            "INSERT INTO job_events(job_id,event_type,payload) VALUES(%s,%s,%s)",
            (job_id, "person_cutout_applied" if payload.enabled else "person_cutout_removed",
             Jsonb({"version": version, "based_on_version": payload.edit_version,
                    "comparison_key": payload.comparison_key if payload.enabled else None,
                    "additional_model_calls": 0, "original_version_retained": True})),
        )
    return {**row, "preview_available": False}


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
