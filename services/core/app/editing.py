from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.config import get_settings
from app.database import connection
from app.edit_plan import MontageEditPlan, TalkingHeadEditPlan, document_sha256, validate_edit_plan
from app.editor_context import build_editor_context
from app.media_analysis import resolve_source
from app.schemas import (
    ApprovalCreate,
    EditRunResponse,
    FinalExportResponse,
    JobReviewResponse,
    UsageDashboardResponse,
    RevisionCreate,
)


router = APIRouter(prefix="/api/v1", tags=["editing"])


def _job_usage(database: Any, job_id: UUID) -> dict[str, Any]:
    events = database.execute(
        """
        SELECT id, job_id, edit_run_id, provider, model, reasoning_effort,
               request_kind, input_tokens, cached_input_tokens, output_tokens,
               reasoning_tokens, total_tokens, latency_ms, created_at
        FROM ai_usage_events
        WHERE job_id = %s
        ORDER BY created_at DESC
        """,
        (job_id,),
    ).fetchall()
    return {
        "requests": len(events),
        "input_tokens": sum(int(row["input_tokens"]) for row in events),
        "cached_input_tokens": sum(int(row["cached_input_tokens"]) for row in events),
        "output_tokens": sum(int(row["output_tokens"]) for row in events),
        "reasoning_tokens": sum(int(row["reasoning_tokens"]) for row in events),
        "total_tokens": sum(int(row["total_tokens"]) for row in events),
        "latency_ms": sum(int(row["latency_ms"]) for row in events),
        "events": list(events),
    }


@router.get("/usage", response_model=UsageDashboardResponse)
def usage_dashboard(days: int = Query(default=0, ge=0, le=3650)) -> dict[str, Any]:
    with connection() as database:
        total = database.execute(
            """
            SELECT count(*) AS requests, count(DISTINCT job_id) AS jobs,
                   COALESCE(sum(input_tokens), 0) AS input_tokens,
                   COALESCE(sum(cached_input_tokens), 0) AS cached_input_tokens,
                   COALESCE(sum(output_tokens), 0) AS output_tokens,
                   COALESCE(sum(reasoning_tokens), 0) AS reasoning_tokens,
                   COALESCE(sum(total_tokens), 0) AS total_tokens
            FROM ai_usage_events
            WHERE %s = 0 OR created_at >= now() - (%s * interval '1 day')
            """,
            (days, days),
        ).fetchone()
        job_count = database.execute(
            """
            SELECT count(*) AS jobs
            FROM jobs
            WHERE %s = 0 OR created_at >= now() - (%s * interval '1 day')
            """,
            (days, days),
        ).fetchone()
        by_model = database.execute(
            """
            SELECT model, count(*) AS requests, COALESCE(sum(total_tokens), 0) AS total_tokens
            FROM ai_usage_events
            WHERE %s = 0 OR created_at >= now() - (%s * interval '1 day')
            GROUP BY model
            ORDER BY total_tokens DESC, model
            """,
            (days, days),
        ).fetchall()
        job_history = database.execute(
            """
            SELECT jobs.id, projects.name AS project_name, jobs.recipe,
                   jobs.status, jobs.created_at,
                   COALESCE(latest_usage.model, latest_run.model, jobs.editor_model) AS model,
                   count(ai_usage_events.id) AS requests,
                   COALESCE(sum(ai_usage_events.total_tokens), 0) AS total_tokens
            FROM jobs
            JOIN projects ON projects.id = jobs.project_id
            LEFT JOIN ai_usage_events ON ai_usage_events.job_id = jobs.id
            LEFT JOIN LATERAL (
                SELECT model
                FROM ai_usage_events AS recent_usage
                WHERE recent_usage.job_id = jobs.id
                ORDER BY recent_usage.created_at DESC
                LIMIT 1
            ) AS latest_usage ON true
            LEFT JOIN LATERAL (
                SELECT model
                FROM edit_runs
                WHERE edit_runs.job_id = jobs.id AND model IS NOT NULL
                ORDER BY version DESC, created_at DESC
                LIMIT 1
            ) AS latest_run ON true
            WHERE %s = 0 OR jobs.created_at >= now() - (%s * interval '1 day')
            GROUP BY jobs.id, projects.name, latest_usage.model, latest_run.model
            ORDER BY jobs.created_at DESC
            """,
            (days, days),
        ).fetchall()
    assert total is not None
    assert job_count is not None
    return {
        "days": days,
        **total,
        "jobs": int(job_count["jobs"]),
        "by_model": list(by_model),
        "job_history": list(job_history),
    }


def _response(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "preview_available": row.get("status") == "ready" and bool(row.get("preview_path"))}


def _final_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "files_available": row.get("status") == "ready"
        and all(
            row.get(key)
            for key in ("video_path", "captions_path", "cover_path", "package_path", "manifest_path")
        ),
        "post_copy_available": row.get("status") == "ready" and bool(row.get("post_copy_path")),
    }


def _needs_montage_delivery_refresh(job: dict[str, Any], export: dict[str, Any]) -> bool:
    """Identify approved deliveries made before montage caption provenance."""

    if job.get("recipe") != "montage" or export.get("status") != "ready":
        return False
    manifest = export.get("manifest")
    if not isinstance(manifest, dict):
        return True
    captions = manifest.get("captions")
    return not isinstance(captions, dict) or captions.get("style") != "clean_blue_v1"


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
        failed = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s AND status = 'failed'
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if failed is not None:
            row = database.execute(
                """
                UPDATE edit_runs
                SET status = 'pending', error = NULL, lease_expires_at = NULL,
                    completed_at = NULL, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (failed["id"],),
            ).fetchone()
            database.execute(
                "UPDATE jobs SET status = 'previewing', updated_at = now() WHERE id = %s",
                (job_id,),
            )
            database.execute(
                """
                INSERT INTO job_events (job_id, event_type, payload)
                VALUES (%s, 'preview_retry_requested', %s)
                """,
                (
                    job_id,
                    Jsonb(
                        {
                            "version": failed["version"],
                            "reused_plan": failed["edit_plan_id"] is not None,
                        }
                    ),
                ),
            )
            assert row is not None
            return _response(row)
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
def submit_edit_plan(
    job_id: UUID, payload: TalkingHeadEditPlan | MontageEditPlan
) -> dict[str, Any]:
    context = _context_or_http(job_id)
    if not context["ready_for_editing"]:
        raise HTTPException(status_code=409, detail="source analysis is not ready")
    document = payload.model_dump(mode="json")
    try:
        plan = validate_edit_plan(
            document,
            context["assets"],
            allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
            creative_direction=context["job"],
            music_tracks=context["music_library"],
        )
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
def preview_file(
    job_id: UUID,
    download: bool = Query(default=False),
    version: int | None = Query(default=None, ge=1),
) -> FileResponse:
    with connection() as database:
        row = database.execute(
            """
            SELECT preview_path, version FROM edit_runs
            WHERE job_id = %s AND status = 'ready'
              AND (%s::integer IS NULL OR version = %s)
            ORDER BY version DESC LIMIT 1
            """,
            (job_id, version, version),
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


def _validate_caption_corrections(
    context: dict[str, Any], corrections: list[dict[str, str]]
) -> None:
    transcript_text = [
        str(segment.get("text", ""))
        for asset in context["assets"]
        for segment in asset.get("transcript_segments", [])
        if isinstance(segment, dict)
    ]
    for correction in corrections:
        original = correction["original_text"]
        if not any(original in text for text in transcript_text):
            raise HTTPException(
                status_code=422,
                detail=f"caption text was not found in this job transcript: {original}",
            )


@router.post(
    "/jobs/{job_id}/revisions",
    response_model=EditRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_revision(job_id: UUID, payload: RevisionCreate) -> dict[str, Any]:
    context = _context_or_http(job_id)
    if not context["ready_for_editing"]:
        raise HTTPException(status_code=409, detail="source analysis is not ready")
    corrections = [item.model_dump() for item in payload.caption_corrections]
    _validate_caption_corrections(context, corrections)
    if context["project"]["privacy_mode"] == "local_only" and payload.note:
        raise HTTPException(
            status_code=409,
            detail="local-only jobs support caption corrections but not editorial replanning",
        )

    with connection() as database:
        job = database.execute(
            "SELECT id FROM jobs WHERE id = %s FOR UPDATE", (job_id,)
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        active = database.execute(
            """
            SELECT 1 FROM edit_runs
            WHERE job_id = %s AND status IN ('pending', 'planning', 'rendering')
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if active is not None:
            raise HTTPException(status_code=409, detail="another edit version is still running")
        based_on = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s AND status = 'ready' AND edit_plan_id IS NOT NULL
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if based_on is None:
            raise HTTPException(status_code=409, detail="a ready preview is required before revision")
        version = database.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS version FROM edit_runs WHERE job_id = %s",
            (job_id,),
        ).fetchone()["version"]
        row = database.execute(
            """
            INSERT INTO edit_runs (
                job_id, version, based_on_run_id, revision_note, caption_corrections
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (job_id, version, based_on["id"], payload.note or None, Jsonb(corrections)),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = 'revising', updated_at = now() WHERE id = %s",
            (job_id,),
        )
        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            VALUES (%s, 'revision_requested', %s)
            """,
            (
                job_id,
                Jsonb(
                    {
                        "version": version,
                        "based_on_version": based_on["version"],
                        "note": payload.note,
                        "caption_correction_count": len(corrections),
                    }
                ),
            ),
        )
    assert row is not None
    return _response(row)


def _select_final_export(
    database: Any,
    job_id: UUID,
    edit_run_id: UUID | None = None,
) -> dict[str, Any] | None:
    if edit_run_id is not None:
        return database.execute(
            """
            SELECT final_exports.*, edit_runs.version
            FROM final_exports
            JOIN edit_runs ON edit_runs.id = final_exports.edit_run_id
            WHERE final_exports.job_id = %s AND final_exports.edit_run_id = %s
            """,
            (job_id, edit_run_id),
        ).fetchone()
    return database.execute(
        """
        SELECT final_exports.*, edit_runs.version
        FROM final_exports
        JOIN edit_runs ON edit_runs.id = final_exports.edit_run_id
        WHERE final_exports.job_id = %s
        ORDER BY final_exports.created_at DESC LIMIT 1
        """,
        (job_id,),
    ).fetchone()


@router.post(
    "/jobs/{job_id}/approval",
    response_model=FinalExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_edit(job_id: UUID, payload: ApprovalCreate) -> dict[str, Any]:
    with connection() as database:
        job = database.execute(
            "SELECT id, recipe FROM jobs WHERE id = %s FOR UPDATE", (job_id,)
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        run = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s AND version = %s AND status = 'ready'
                  AND edit_plan_id IS NOT NULL AND preview_path IS NOT NULL
            """,
            (job_id, payload.version),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=409, detail="the requested preview version is not ready")
        database.execute(
            """
            INSERT INTO approvals (job_id, edit_plan_id, decision, note)
            SELECT %s, %s, 'approved', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM approvals
                WHERE job_id = %s AND edit_plan_id = %s AND decision = 'approved'
            )
            """,
            (job_id, run["edit_plan_id"], payload.note, job_id, run["edit_plan_id"]),
        )
        database.execute(
            "UPDATE edit_runs SET approved_at = COALESCE(approved_at, now()), updated_at = now() WHERE id = %s",
            (run["id"],),
        )
        database.execute(
            """
            INSERT INTO final_exports (job_id, edit_run_id)
            VALUES (%s, %s)
            ON CONFLICT (edit_run_id) DO NOTHING
            """,
            (job_id, run["id"]),
        )
        database.execute(
            """
            UPDATE final_exports
            SET status = 'pending', attempts = 0, error = NULL,
                lease_expires_at = NULL, updated_at = now()
            WHERE edit_run_id = %s AND status = 'failed'
            """,
            (run["id"],),
        )
        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            SELECT %s, 'edit_approved', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM job_events
                WHERE job_id = %s AND event_type = 'edit_approved'
                  AND (payload->>'version')::integer = %s
            )
            """,
            (job_id, Jsonb({"version": payload.version}), job_id, payload.version),
        )
        row = _select_final_export(database, job_id, run["id"])
        if row is not None and _needs_montage_delivery_refresh(job, row):
            database.execute(
                """
                UPDATE final_exports
                SET status = 'pending', attempts = 0, error = NULL,
                    video_path = NULL, captions_path = NULL, cover_path = NULL,
                    post_copy_path = NULL, package_path = NULL, manifest_path = NULL,
                    manifest = '{}'::jsonb, lease_expires_at = NULL, started_at = NULL,
                    completed_at = NULL, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (row["id"],),
            )
            database.execute(
                """
                INSERT INTO job_events (job_id, event_type, payload)
                VALUES (%s, 'final_export_refresh_requested', %s)
                """,
                (
                    job_id,
                    Jsonb(
                        {
                            "version": run["version"],
                            "reason": "montage_caption_provenance_upgrade",
                        }
                    ),
                ),
            )
            row = _select_final_export(database, job_id, run["id"])
        database.execute(
            "UPDATE jobs SET status = %s, revision = %s, updated_at = now() WHERE id = %s",
            ("delivered" if row and row["status"] == "ready" else "exporting", payload.version, job_id),
        )
    assert row is not None
    return _final_response(row)


@router.get("/jobs/{job_id}/review", response_model=JobReviewResponse)
def job_review(job_id: UUID) -> dict[str, Any]:
    with connection() as database:
        job = database.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        runs = database.execute(
            "SELECT * FROM edit_runs WHERE job_id = %s ORDER BY version DESC",
            (job_id,),
        ).fetchall()
        export = _select_final_export(database, job_id)
        events = database.execute(
            """
            SELECT id, event_type, payload, created_at
            FROM job_events WHERE job_id = %s ORDER BY id DESC LIMIT 30
            """,
            (job_id,),
        ).fetchall()
        usage = _job_usage(database, job_id)
    versions = [_response(row) for row in runs]
    return {
        "job": job,
        "versions": versions,
        "latest_run": versions[0] if versions else None,
        "final_export": _final_response(export) if export is not None else None,
        "events": list(events),
        "usage": usage,
    }


@router.get("/jobs/{job_id}/final", response_model=FinalExportResponse)
def final_status(job_id: UUID) -> dict[str, Any]:
    with connection() as database:
        row = _select_final_export(database, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="a final export has not been requested")
    return _final_response(row)


@router.get("/jobs/{job_id}/final/{file_kind}")
def final_file(job_id: UUID, file_kind: str) -> FileResponse:
    choices = {
        "video": ("video_path", "video/mp4", "gm-studio-final.mp4"),
        "captions": ("captions_path", "text/vtt", "gm-studio-captions.vtt"),
        "cover": ("cover_path", "image/jpeg", "gm-studio-cover.jpg"),
        "post-copy": ("post_copy_path", "text/plain", "gm-studio-post-copy.txt"),
        "manifest": ("manifest_path", "application/json", "gm-studio-manifest.json"),
        "package": ("package_path", "application/zip", "gm-studio-delivery.zip"),
    }
    choice = choices.get(file_kind)
    if choice is None:
        raise HTTPException(status_code=404, detail="unknown final file")
    with connection() as database:
        row = _select_final_export(database, job_id)
    path_key, media_type, filename = choice
    if row is None or row["status"] != "ready" or not row.get(path_key):
        raise HTTPException(status_code=404, detail="final file is not ready")
    try:
        path = resolve_source(get_settings().media_root, str(row[path_key]))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=404, detail="final file is unavailable") from error
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
    )
