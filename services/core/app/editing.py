from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.config import get_settings
from app.database import connection
from app.edit_plan import TalkingHeadEditPlan, document_sha256, validate_edit_plan
from app.editor_context import build_editor_context
from app.media_analysis import resolve_source
from app.schemas import EditRunResponse


router = APIRouter(prefix="/api/v1", tags=["editing"])


def _response(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "preview_available": row.get("status") == "ready" and bool(row.get("preview_path"))}


def _context_or_http(job_id: UUID, *, internal: bool = False) -> dict[str, Any]:
    try:
        return build_editor_context(job_id, include_internal_paths=internal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="job not found") from error


@router.get("/jobs/{job_id}/editor-context")
def editor_context(job_id: UUID) -> dict[str, Any]:
    return _context_or_http(job_id)


@router.post(
    "/jobs/{job_id}/preview",
    response_model=EditRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_preview(job_id: UUID) -> dict[str, Any]:
    context = _context_or_http(job_id)
    if not context["assets"]:
        raise HTTPException(status_code=409, detail="the job has no source media")
    with connection() as database:
        database.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (job_id,)).fetchone()
        existing = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s AND status IN ('pending', 'planning', 'rendering', 'ready')
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if existing is not None:
            return _response(existing)
        version = database.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS version FROM edit_runs WHERE job_id = %s",
            (job_id,),
        ).fetchone()["version"]
        row = database.execute(
            """
            INSERT INTO edit_runs (job_id, version)
            VALUES (%s, %s)
            RETURNING *
            """,
            (job_id, version),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = 'planning', updated_at = now() WHERE id = %s",
            (job_id,),
        )
        database.execute(
            "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'preview_requested', %s)",
            (job_id, Jsonb({"version": version})),
        )
    assert row is not None
    return _response(row)


@router.post(
    "/jobs/{job_id}/edit-plans",
    response_model=EditRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_edit_plan(job_id: UUID, payload: TalkingHeadEditPlan) -> dict[str, Any]:
    context = _context_or_http(job_id)
    if not context["ready_for_editing"]:
        raise HTTPException(status_code=409, detail="source analysis is not ready")
    document = payload.model_dump(mode="json")
    try:
        plan = validate_edit_plan(document, context["assets"])
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    with connection() as database:
        database.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (job_id,)).fetchone()
        version = database.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS version FROM edit_runs WHERE job_id = %s",
            (job_id,),
        ).fetchone()["version"]
        plan_row = database.execute(
            """
            INSERT INTO edit_plans (
                job_id, version, schema_version, document, provider, model, document_sha256
            ) VALUES (%s, %s, %s, %s, 'submitted', 'validated_edl', %s)
            RETURNING id
            """,
            (
                job_id,
                version,
                plan.schema_version,
                Jsonb(plan.model_dump(mode="json")),
                document_sha256(plan.model_dump(mode="json")),
            ),
        ).fetchone()
        row = database.execute(
            """
            INSERT INTO edit_runs (
                job_id, version, status, edit_plan_id, provider, model
            ) VALUES (%s, %s, 'pending', %s, 'submitted', 'validated_edl')
            RETURNING *
            """,
            (job_id, version, plan_row["id"]),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = 'previewing', updated_at = now() WHERE id = %s",
            (job_id,),
        )
        database.execute(
            "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'edit_plan_submitted', %s)",
            (job_id, Jsonb({"version": version, "edit_plan_id": str(plan_row["id"])})),
        )
    assert row is not None
    return _response(row)


@router.get("/jobs/{job_id}/preview", response_model=EditRunResponse)
def preview_status(job_id: UUID) -> dict[str, Any]:
    with connection() as database:
        job = database.execute("SELECT 1 FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        row = database.execute(
            "SELECT * FROM edit_runs WHERE job_id = %s ORDER BY version DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="preview has not been requested")
    return _response(row)


@router.get("/jobs/{job_id}/preview/file")
def preview_file(job_id: UUID, download: bool = Query(default=False)) -> FileResponse:
    with connection() as database:
        row = database.execute(
            """
            SELECT preview_path, version FROM edit_runs
            WHERE job_id = %s AND status = 'ready'
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if row is None or not row["preview_path"]:
        raise HTTPException(status_code=404, detail="preview is not ready")
    try:
        path = resolve_source(get_settings().media_root, str(row["preview_path"]))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=404, detail="preview file is unavailable") from error
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"gm-studio-preview-v{row['version']}.mp4",
        content_disposition_type=disposition,
    )
