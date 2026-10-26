import re
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.caption_text import caption_phrase_exists
from app.config import get_settings
from app.database import connection
from app.edit_plan import (
    MontageEditPlan,
    TalkingHeadEditPlan,
    document_sha256,
    clip_handle,
    apply_timeline_adjustments,
    repair_predictable_plan_defaults,
    source_word_gaps,
    validate_edit_plan,
)
from app.editor_context import build_editor_context
from app.media_analysis import resolve_source
from app.productization import assert_job_capacity
from app.schemas import (
    ApprovalCreate,
    CoverFrameUpdate,
    DeliveryVariantCreate,
    DeliveryVariantResponse,
    EditRunResponse,
    FinalExportResponse,
    JobReviewResponse,
    PromptHistoryResponse,
    UsageDashboardResponse,
    RevisionCreate,
    JobResponse,
)


router = APIRouter(prefix="/api/v1", tags=["editing"])


@router.put("/jobs/{job_id}/cover-frame", response_model=JobResponse)
def update_cover_frame(job_id: UUID, payload: CoverFrameUpdate) -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            "UPDATE jobs SET cover_time_seconds=%s, updated_at=now() WHERE id=%s RETURNING *",
            (payload.time_seconds, job_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row

VERIFICATION_PROJECT_PATTERN = re.compile(
    r"^Phase\s+\d+[A-Z]*\s+(?:(?:library|effects)\s+)?verification(?:\s|—|$)",
    re.IGNORECASE,
)


def _job_history_kind(project_name: str) -> str:
    return "verification" if VERIFICATION_PROJECT_PATTERN.search(project_name) else "editing"


@router.get("/prompt-history", response_model=PromptHistoryResponse)
def prompt_history(
    query: str = Query(default="", max_length=500),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Original briefs are immutable project data. Revision notes are retained on
    # edit runs independently of the short operational event feed and exports.
    with connection() as database:
        rows = database.execute(
            """
            WITH history AS (
                SELECT 'original:' || jobs.id::text AS id, jobs.id AS job_id,
                       projects.name AS project_name, projects.brief AS prompt,
                       'original' AS kind, NULL::integer AS version, jobs.status,
                       jobs.created_at, jobs.archived_at IS NOT NULL AS archived
                FROM jobs JOIN projects ON projects.id = jobs.project_id
                WHERE btrim(projects.brief) <> ''
                UNION ALL
                SELECT 'revision:' || edit_runs.id::text, jobs.id, projects.name,
                       edit_runs.revision_note, 'revision', edit_runs.version,
                       edit_runs.status, edit_runs.created_at,
                       jobs.archived_at IS NOT NULL
                FROM edit_runs JOIN jobs ON jobs.id = edit_runs.job_id
                JOIN projects ON projects.id = jobs.project_id
                WHERE btrim(coalesce(edit_runs.revision_note, '')) <> ''
            )
            SELECT * FROM history
            WHERE project_name !~* %s
              AND (%s = '' OR strpos(lower(project_name || ' ' || prompt), lower(%s)) > 0)
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (VERIFICATION_PROJECT_PATTERN.pattern, query.strip(), query.strip(), limit + 1, offset),
        ).fetchall()
    items = list(rows[:limit])
    return {"items": items, "has_more": len(rows) > limit, "next_offset": offset + len(items)}


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
                   count(*) FILTER (WHERE request_kind='concepts') AS concept_requests,
                   COALESCE(sum(total_tokens) FILTER (WHERE request_kind='concepts'),0) AS concept_tokens,
                   count(*) FILTER (WHERE request_kind='organization') AS organization_requests,
                   COALESCE(sum(total_tokens) FILTER (WHERE request_kind='organization'),0) AS organization_tokens,
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
            SELECT jobs.id, projects.name AS project_name, jobs.recipe, jobs.reel_intent,
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
        for job in job_history:
            job["history_kind"] = _job_history_kind(str(job["project_name"]))
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


def _variant_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "files_available": row.get("status") == "ready"
        and all(row.get(key) for key in ("video_path", "captions_path", "cover_path", "package_path", "manifest_path")),
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


def _editorial_timeline(document: dict[str, Any] | None, context: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    assets = {str(item["asset_id"]): item for item in context["assets"]}
    result: list[dict[str, Any]] = []
    for index, clip in enumerate(document.get("clips") or []):
        if not isinstance(clip, dict):
            continue
        asset_id = str(clip.get("asset_id") or "")
        asset = assets.get(asset_id)
        if asset is None:
            continue
        source_in = float(clip.get("source_in") or 0)
        source_out = float(clip.get("source_out") or source_in)
        excerpts = []
        for segment in asset.get("transcript_segments", []):
            if not isinstance(segment, dict):
                continue
            if float(segment.get("end") or 0) > source_in and float(segment.get("start") or 0) < source_out:
                text = " ".join(str(segment.get("text") or "").split())
                if text:
                    excerpts.append(text)
        media_kind = str(clip.get("media_kind") or "video")
        pauses = source_word_gaps(asset, source_in, source_out)
        result.append(
            {
                "clip_index": index,
                "clip_id": clip_handle(index, clip),
                "words": [{"text": str(word.get("text", "")), "start": float(word["start"]), "end": float(word["end"])}
                          for segment in asset.get("transcript_segments", []) for word in segment.get("words", [])
                          if float(word.get("end", 0)) > source_in and float(word.get("start", 0)) < source_out][:160],
                "asset_id": asset_id,
                "source_name": asset["source_name"],
                "media_kind": media_kind,
                "source_in": source_in,
                "source_out": source_out,
                "duration": float(clip.get("duration") or max(0, source_out - source_in)),
                "transition": str(clip.get("transition") or "cut"),
                "visual_preset": str(clip.get("visual_preset") or "standard"),
                "include_source_audio": bool(clip.get("include_source_audio", media_kind == "video")),
                "source_audio_gain_db": float(clip.get("source_audio_gain_db") or 0),
                "transcript_excerpt": " ".join(excerpts)[:320],
                "story_role": str(clip.get("story_role") or "development"),
                "editorial_intent": str(clip.get("editorial_intent") or "")[:180],
                "longest_pause_seconds": round(
                    max((gap[2] for gap in pauses), default=0.0), 3
                ),
            }
        )
    return result


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
        latest = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if latest is not None and latest["status"] == "ready" and not latest.get("preview_path"):
            assert_job_capacity(database, job_id)
            row = database.execute(
                """
                UPDATE edit_runs SET status='pending', error=NULL, lease_expires_at=NULL,
                    completed_at=NULL, updated_at=now() WHERE id=%s RETURNING *
                """,
                (latest["id"],),
            ).fetchone()
            database.execute("UPDATE jobs SET status='previewing', updated_at=now() WHERE id=%s", (job_id,))
            database.execute(
                "INSERT INTO job_events (job_id,event_type,payload) VALUES (%s,'retained_preview_rebuild_requested',%s)",
                (job_id, Jsonb({"version": latest["version"], "reused_plan": True})),
            )
            assert row is not None
            return _response(row)
        if latest is not None and latest["status"] in {
            "pending",
            "planning",
            "rendering",
            "ready",
        }:
            return _response(latest)
        if latest is not None and latest["status"] == "failed":
            assert_job_capacity(database, job_id)
            row = database.execute(
                """
                UPDATE edit_runs
                SET status = 'pending', error = NULL, lease_expires_at = NULL,
                    completed_at = NULL, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (latest["id"],),
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
                            "version": latest["version"],
                            "reused_plan": latest["edit_plan_id"] is not None,
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
        assert_job_capacity(database, job_id)
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
    "/jobs/{job_id}/preview/rebuild",
    response_model=EditRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def rebuild_preview(job_id: UUID) -> dict[str, Any]:
    """Render the latest accepted plan again without another hosted model call."""

    context = _context_or_http(job_id)
    if not context["ready_for_editing"]:
        raise HTTPException(status_code=409, detail="source analysis is not ready")
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
            raise HTTPException(status_code=409, detail="a ready preview is required before rebuilding")
        assert_job_capacity(database, job_id)
        version = database.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS version FROM edit_runs WHERE job_id = %s",
            (job_id,),
        ).fetchone()["version"]
        row = database.execute(
            """
            INSERT INTO edit_runs (
                job_id, version, edit_plan_id, based_on_run_id, provider, model,
                reasoning_effort, caption_corrections, locked_elements
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                job_id,
                version,
                based_on["edit_plan_id"],
                based_on["id"],
                based_on.get("provider"),
                based_on.get("model"),
                based_on.get("reasoning_effort"),
                Jsonb(based_on.get("caption_corrections") or []),
                Jsonb(based_on.get("locked_elements") or []),
            ),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = 'previewing', updated_at = now() WHERE id = %s",
            (job_id,),
        )
        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            VALUES (%s, 'preview_rebuild_requested', %s)
            """,
            (
                job_id,
                Jsonb(
                    {
                        "version": version,
                        "based_on_version": based_on["version"],
                        "reused_plan": True,
                        "additional_model_calls": 0,
                    }
                ),
            ),
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
            creative_effects=context["creative_effect_library"],
        )
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    with connection() as database:
        database.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (job_id,)).fetchone()
        assert_job_capacity(database, job_id)
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
    transcript_text: list[str] = []
    for asset in context["assets"]:
        for segment in asset.get("transcript_segments", []):
            if not isinstance(segment, dict):
                continue
            transcript_text.append(str(segment.get("text", "")))
            word_text = " ".join(
                str(word.get("text") or "")
                for word in segment.get("words", [])
                if isinstance(word, dict)
            )
            if word_text:
                transcript_text.append(word_text)
    for correction in corrections:
        original = correction["original_text"]
        if not any(caption_phrase_exists(text, original) for text in transcript_text):
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
    adjustments = [
        item.model_dump(mode="json", exclude_none=True)
        for item in payload.clip_adjustments
    ]
    _validate_caption_corrections(context, corrections)
    if context["project"]["privacy_mode"] == "local_only" and (
        payload.note or payload.evaluation_lesson_id
    ):
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
        assert_job_capacity(database, job_id)
        active = database.execute(
            """
            SELECT 1 FROM edit_runs
            WHERE job_id = %s AND status IN ('pending', 'planning', 'rendering')
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if active is not None:
            raise HTTPException(
                status_code=409, detail="another edit version is still running"
            )
        based_on = database.execute(
            """
            SELECT * FROM edit_runs
            WHERE job_id = %s AND status = 'ready' AND edit_plan_id IS NOT NULL
            ORDER BY version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if based_on is None:
            raise HTTPException(
                status_code=409, detail="a ready preview is required before revision"
            )
        if (
            payload.base_version is not None
            and payload.base_version != based_on["version"]
        ):
            raise HTTPException(
                status_code=409,
                detail="this preview changed; refresh before submitting edits",
            )
        if payload.restore_version is not None:
            if payload.note or adjustments or payload.caption_corrections:
                raise HTTPException(
                    status_code=422,
                    detail="restore a version separately from other edit changes",
                )
            based_on = database.execute(
                "SELECT * FROM edit_runs WHERE job_id=%s AND version=%s AND status='ready' AND edit_plan_id IS NOT NULL",
                (job_id, payload.restore_version),
            ).fetchone()
            if not based_on:
                raise HTTPException(
                    status_code=404,
                    detail="a ready version with that number was not found",
                )
        if payload.finishing_settings is not None or adjustments:
            source_plan = database.execute(
                "SELECT document FROM edit_plans WHERE id=%s",
                (based_on["edit_plan_id"],),
            ).fetchone()
            if not source_plan:
                raise HTTPException(
                    status_code=409, detail="the source edit plan is unavailable"
                )
            try:
                previous_document, _ = repair_predictable_plan_defaults(
                    source_plan["document"],
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                    creative_effects=context["creative_effect_library"],
                )
                options = {
                    "allow_post_copy": bool(context["project"]["ai_copy_allowed"]),
                    "creative_direction": context["job"],
                    "music_tracks": context["music_library"],
                    "creative_effects": context["creative_effect_library"],
                }
                candidate = validate_edit_plan(
                    previous_document, context["assets"], **options
                )
                if adjustments:
                    candidate = apply_timeline_adjustments(
                        candidate, adjustments, context["assets"]
                    )
                document = candidate.model_dump(mode="json")
                if payload.finishing_settings is not None:
                    document.update(
                        schema_version="1.5",
                        finishing=payload.finishing_settings.model_dump(mode="json"),
                    )
                validate_edit_plan(document, context["assets"], **options)
            except (ValueError, ValidationError) as error:
                raise HTTPException(status_code=422, detail=str(error)[:500]) from error
        if payload.evaluation_lesson_id is not None:
            from app.learning_lab import lesson, assert_holdout

            candidate_lesson = lesson(database, payload.evaluation_lesson_id)
            if candidate_lesson["status"] != "proposed":
                raise HTTPException(
                    status_code=409,
                    detail="only a proposed lesson can be tried as a held-out experiment",
                )
            assert_holdout(database, candidate_lesson, job_id)
            payload.note = candidate_lesson["directive"]
        if payload.repair_kind is not None:
            existing_repair = database.execute(
                "SELECT * FROM edit_runs WHERE based_on_run_id=%s AND repair_kind IS NOT NULL",
                (based_on["id"],),
            ).fetchone()
            if existing_repair:
                raise HTTPException(
                    status_code=409,
                    detail="one local repair has already been attempted on this version; review it before making another change",
                )
            if payload.note or payload.evaluation_lesson_id:
                raise HTTPException(
                    status_code=422,
                    detail="local repairs cannot request model replanning",
                )
        inherited_corrections = list(based_on.get("caption_corrections") or [])
        replacement_targets = {
            str(item.get("original_text") or "").casefold() for item in corrections
        }
        effective_corrections = [
            item
            for item in inherited_corrections
            if str(item.get("original_text") or "").casefold()
            not in replacement_targets
        ] + corrections
        effective_caption_settings = (
            payload.caption_settings.model_dump()
            if payload.caption_settings is not None
            else dict(based_on.get("caption_settings") or {})
        )
        version = database.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS version FROM edit_runs WHERE job_id = %s",
            (job_id,),
        ).fetchone()["version"]
        row = database.execute(
            """
            INSERT INTO edit_runs (
                job_id, version, based_on_run_id, revision_note, caption_corrections,
                caption_settings, effects_enabled, clip_adjustments, locked_elements, revision_mode, broll_enabled, finishing_settings, evaluation_lesson_id, repair_kind
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                job_id,
                version,
                based_on["id"],
                payload.note or None,
                Jsonb(effective_corrections),
                Jsonb(effective_caption_settings),
                payload.effects_enabled,
                Jsonb(adjustments),
                Jsonb(payload.locked_elements),
                payload.revision_mode,
                payload.broll_enabled,
                Jsonb(payload.finishing_settings.model_dump(mode="json"))
                if payload.finishing_settings is not None
                else None,
                payload.evaluation_lesson_id,
                payload.repair_kind,
            ),
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
                        "revision_mode": payload.revision_mode,
                        "caption_correction_count": len(effective_corrections),
                        "caption_settings": effective_caption_settings,
                        "effects_enabled": payload.effects_enabled,
                        "broll_enabled": payload.broll_enabled,
                        "timeline_adjustment_count": len(adjustments),
                        "locked_elements": payload.locked_elements,
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
        assert_job_capacity(database, job_id)
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
        if row is not None and row["status"] == "ready" and not row.get("package_path"):
            database.execute(
                """
                UPDATE final_exports SET status='pending', attempts=0, error=NULL,
                    lease_expires_at=NULL, started_at=NULL, completed_at=NULL, updated_at=now()
                WHERE id=%s
                """,
                (row["id"],),
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
        variants = database.execute(
            """
            SELECT delivery_variants.*, edit_runs.version
            FROM delivery_variants
            JOIN edit_runs ON edit_runs.id = delivery_variants.edit_run_id
            WHERE delivery_variants.job_id = %s
            ORDER BY delivery_variants.created_at DESC
            """,
            (job_id,),
        ).fetchall()
        events = database.execute(
            """
            SELECT id, event_type, payload, created_at
            FROM job_events WHERE job_id = %s ORDER BY id DESC LIMIT 30
            """,
            (job_id,),
        ).fetchall()
        usage = _job_usage(database, job_id)
        plan_row = database.execute(
            """
            SELECT edit_plans.document FROM edit_runs
            JOIN edit_plans ON edit_plans.id = edit_runs.edit_plan_id
            WHERE edit_runs.job_id = %s ORDER BY edit_runs.version DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        brand_kit = None
        if job.get("brand_kit_id") is not None:
            brand_kit = database.execute("SELECT * FROM brand_kits WHERE id=%s", (job["brand_kit_id"],)).fetchone()
        latest_feedback = None
        if runs:
            latest_feedback = database.execute(
                "SELECT * FROM edit_feedback WHERE edit_run_id=%s",
                (runs[0]["id"],),
            ).fetchone()
    context = _context_or_http(job_id)
    versions = [_response(row) for row in runs]
    return {
        "job": job,
        "original_prompt": context["project"]["brief"],
        "project_name": context["project"]["name"],
        "versions": versions,
        "latest_run": versions[0] if versions else None,
        "final_export": _final_response(export) if export is not None else None,
        "delivery_variants": [_variant_response(row) for row in variants],
        "editorial_timeline": _editorial_timeline(plan_row["document"] if plan_row else None, context),
        "story_assessment": context.get("story_spine", {}).get("engagement_assessment", {}),
        "brand_kit": brand_kit,
        "latest_feedback": latest_feedback,
        "events": list(events),
        "usage": usage,
    }


@router.post(
    "/jobs/{job_id}/variants",
    response_model=DeliveryVariantResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_delivery_variant(job_id: UUID, payload: DeliveryVariantCreate) -> dict[str, Any]:
    with connection() as database:
        assert_job_capacity(database, job_id)
        selected = database.execute(
            """
            SELECT final_exports.edit_run_id, edit_runs.version
            FROM final_exports
            JOIN edit_runs ON edit_runs.id = final_exports.edit_run_id
            WHERE final_exports.job_id = %s AND final_exports.status = 'ready'
              AND edit_runs.approved_at IS NOT NULL
            ORDER BY final_exports.created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if selected is None:
            raise HTTPException(status_code=409, detail="approve and finish a final delivery before creating variants")
        row = database.execute(
            """
            INSERT INTO delivery_variants (
                job_id, edit_run_id, output_aspect, target_duration_seconds
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (edit_run_id, output_aspect, target_duration_seconds)
            DO UPDATE SET
                status = CASE WHEN delivery_variants.status = 'failed' THEN 'pending' ELSE delivery_variants.status END,
                attempts = CASE WHEN delivery_variants.status = 'failed' THEN 0 ELSE delivery_variants.attempts END,
                error = CASE WHEN delivery_variants.status = 'failed' THEN NULL ELSE delivery_variants.error END,
                lease_expires_at = NULL,
                updated_at = now()
            RETURNING *
            """,
            (
                job_id,
                selected["edit_run_id"],
                payload.output_aspect.value,
                payload.target_duration_seconds,
            ),
        ).fetchone()
        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            VALUES (%s, 'delivery_variant_requested', %s)
            """,
            (
                job_id,
                Jsonb(
                    {
                        "version": selected["version"],
                        "output_aspect": payload.output_aspect.value,
                        "target_duration_seconds": payload.target_duration_seconds,
                    }
                ),
            ),
        )
    assert row is not None
    return _variant_response({**row, "version": selected["version"]})


@router.get("/jobs/{job_id}/variants/{variant_id}/{file_kind}")
def delivery_variant_file(
    job_id: UUID, variant_id: UUID, file_kind: str, download: bool = Query(default=True)
) -> FileResponse:
    choices = {
        "video": ("video_path", "video/mp4", "gm-studio-variant.mp4"),
        "captions": ("captions_path", "text/vtt", "gm-studio-variant-captions.vtt"),
        "cover": ("cover_path", "image/jpeg", "gm-studio-variant-cover.jpg"),
        "manifest": ("manifest_path", "application/json", "gm-studio-variant-manifest.json"),
        "package": ("package_path", "application/zip", "gm-studio-variant-delivery.zip"),
    }
    choice = choices.get(file_kind)
    if choice is None:
        raise HTTPException(status_code=404, detail="unknown variant file")
    with connection() as database:
        row = database.execute(
            "SELECT * FROM delivery_variants WHERE id = %s AND job_id = %s",
            (variant_id, job_id),
        ).fetchone()
    path_key, media_type, filename = choice
    if row is None or row["status"] != "ready" or not row.get(path_key):
        raise HTTPException(status_code=404, detail="variant file is not ready")
    try:
        path = resolve_source(get_settings().media_root, str(row[path_key]))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=404, detail="variant file is unavailable") from error
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


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


@router.get("/jobs/{job_id}/finishing-tools")
def inspect_finishing_tools(job_id: UUID):
    context = _context_or_http(job_id)
    with connection() as database:
        row = database.execute(
            """SELECT r.version, p.document FROM edit_runs r JOIN edit_plans p ON p.id=r.edit_plan_id
            WHERE r.job_id=%s AND r.status='ready' ORDER BY r.version DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="a ready preview is required")
    from app.finishing_tools import FinishingTools

    return {
        "version": row["version"],
        "settings": row["document"].get("finishing")
        or FinishingTools().model_dump(mode="json"),
        "clips": [
            {key: value for key, value in clip.items() if key != "words"}
            for clip in _editorial_timeline(row["document"], context)
        ],
        "sources": [
            {
                "asset_id": str(a["asset_id"]),
                "name": a.get("library_name") or a["source_name"],
                "media_kind": "image"
                if str(a.get("mime_type", "")).startswith("image/")
                else "video",
                "duration_seconds": a.get("duration_seconds") or 0,
            }
            for a in context["assets"]
            if a.get("has_video") or str(a.get("mime_type", "")).startswith("image/")
        ],
        "capabilities": {
            "keyframes": True,
            "phrase_audio": True,
            "cue_captions": True,
            "picture_layers": True,
            "green_screen": True,
            "visual_retiming": True,
            "independent_audio_joins": True,
            "ai_background_removal": False,
            "automatic_tracking": False,
        },
        "hosted_model_calls": 0,
    }


class LocalRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: int = Field(gt=0)
    action: Literal["tighten_pauses", "denoise"]


@router.post("/jobs/{job_id}/local-repair")
def local_repair(job_id: UUID, payload: LocalRepairRequest):
    tools = inspect_finishing_tools(job_id)
    if tools["version"] != payload.base_version:
        raise HTTPException(
            status_code=409, detail="refresh this preview before requesting a repair"
        )
    if payload.action == "denoise":
        from app.finishing_tools import FinishingTools

        settings = FinishingTools.model_validate(
            {**tools["settings"], "voice_denoise": True}
        )
        request = RevisionCreate(
            base_version=payload.base_version,
            finishing_settings=settings,
            repair_kind="denoise",
        )
    else:
        review = job_review(job_id)
        changes = [
            {
                "clip_index": c["clip_index"],
                "clip_id": c["clip_id"],
                "max_pause_seconds": 0.6,
            }
            for c in reversed(review["editorial_timeline"])
            if c["media_kind"] == "video" and c["longest_pause_seconds"] > 0.7
        ]
        if not changes:
            raise HTTPException(
                status_code=409,
                detail="no long speech gap was detected; use a precise trim for the moment you want changed",
            )
        request = RevisionCreate(
            base_version=payload.base_version,
            clip_adjustments=changes,
            repair_kind="tighten_pauses",
        )
    return request_revision(job_id, request)


@router.get("/jobs/{job_id}/hook-options")
def hook_options(job_id: UUID):
    from app.edit_plan import apply_timeline_adjustments

    context = _context_or_http(job_id)
    with connection() as database:
        source = database.execute(
            """SELECT r.version,p.document FROM edit_runs r JOIN edit_plans p ON p.id=r.edit_plan_id
            WHERE r.job_id=%s AND r.status='ready' ORDER BY r.version DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
    if not source:
        raise HTTPException(status_code=409, detail="a ready preview is required")
    options = []
    candidates = []
    for asset in context["assets"]:
        if (
            not asset.get("has_video")
            or not asset.get("has_audio")
            or asset.get("source_evidence", {}).get("library", {}).get("role")
            == "broll"
        ):
            continue
        for moment in asset.get("story_index", {}).get("moments", []):
            if moment.get("kind") == "spoken" and "hook" in moment.get(
                "suggested_roles", []
            ):
                candidates.append(
                    (float(moment.get("role_scores", {}).get("hook", 0)), asset, moment)
                )
    kwargs = {
        "allow_post_copy": bool(context["project"]["ai_copy_allowed"]),
        "creative_direction": context["job"],
        "music_tracks": context["music_library"],
        "creative_effects": context["creative_effect_library"],
    }
    baseline = validate_edit_plan(source["document"], context["assets"], **kwargs)
    for score, asset, moment in sorted(
        candidates, key=lambda value: value[0], reverse=True
    ):
        start = max(0, float(moment["start_seconds"]) - 0.08)
        end = min(float(asset["duration_seconds"]), float(moment["end_seconds"]) + 0.12)
        if not 0.5 <= end - start <= 8:
            continue
        if any(
            r.get("role") == "avoid"
            and max(start, float(r["start_seconds"]))
            < min(end, float(r["end_seconds"]))
            for r in asset.get("source_evidence", {}).get("user_ranges", [])
        ):
            continue
        if any(
            str(c.asset_id) == str(asset["asset_id"])
            and max(start, c.source_in) < min(end, c.source_out)
            for c in baseline.clips[1:]
        ):
            continue
        adjustment = {
            "clip_index": 0,
            "clip_id": clip_handle(0, source["document"]["clips"][0]),
            "replacement_asset_id": str(asset["asset_id"]),
            "source_in": round(start, 3),
            "source_out": round(end, 3),
            "visual_preset": "standard",
        }
        if (
            str(baseline.clips[0].asset_id) == str(asset["asset_id"])
            and abs(start - baseline.clips[0].source_in) < 0.15
            and abs(end - baseline.clips[0].source_out) < 0.15
        ):
            continue
        try:
            candidate = apply_timeline_adjustments(
                baseline, [adjustment], context["assets"]
            )
            validate_edit_plan(
                candidate.model_dump(mode="json"), context["assets"], **kwargs
            )
        except ValueError:
            continue
        options.append(
            {
                "text": str(moment.get("text", ""))[:600],
                "source_name": asset.get("library_name") or asset["source_name"],
                "adjustment": adjustment,
                "reason": "Locally ranked recorded hook; review its fit with the story.",
            }
        )
        if len(options) == 3:
            break
    return {
        "version": source["version"],
        "options": options,
        "hosted_model_calls": 0,
        "note": "Recorded alternatives only. No new narration or model critique. Empty options mean no safe local replacement qualified.",
    }
