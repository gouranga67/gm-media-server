import json
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from psycopg.types.json import Jsonb
from redis import Redis

from app.config import get_settings
from app.database import connection
from app.edit_plan import EditPlan, MontageEditPlan, document_sha256, validate_edit_plan
from app.edit_renderer import render_edit_preview, render_final_delivery
from app.editor_context import build_editor_context
from app.editor_provider import create_edit_plan, list_chatgpt_models
from app.finalize_upload import finalize_original, upload_source_path
from app.media_analysis import analyze_asset, resolve_source
from app.montage_renderer import render_montage_delivery, render_montage_preview
from app.music_analysis import analyze_music_beats


@dataclass
class WorkerState:
    stopping: bool = False
    active_ingest_id: str | None = None
    active_edit_run_id: str | None = None
    active_final_export_id: str | None = None


def claim_pending_upload() -> dict[str, Any] | None:
    with connection() as database:
        row = database.execute(
            """
            SELECT id, project_id, tus_upload_id, byte_size
            FROM assets
            WHERE status = 'uploaded'
               OR (status = 'quarantined' AND updated_at < now() - interval '10 minutes')
            ORDER BY updated_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        database.execute(
            "UPDATE assets SET status = 'quarantined', updated_at = now() WHERE id = %s",
            (row["id"],),
        )
        return row


def finalize_one_upload() -> bool:
    asset = claim_pending_upload()
    if asset is None:
        return False

    settings = get_settings()
    asset_id = asset["id"]
    project_id = asset["project_id"]
    upload_id = str(asset["tus_upload_id"] or asset_id)
    destination = settings.media_root / "originals" / str(project_id) / str(asset_id) / "source"

    try:
        source = upload_source_path(settings.upload_root, upload_id)
        digest = finalize_original(source, destination, int(asset["byte_size"]))
        relative_path = destination.relative_to(settings.media_root).as_posix()
        with connection() as database:
            database.execute(
                """
                UPDATE assets
                SET status = 'ready', sha256 = %s, storage_key = %s,
                    metadata = metadata - 'finalize_error', updated_at = now()
                WHERE id = %s
                """,
                (digest, relative_path, asset_id),
            )
        print(f"asset ready: {asset_id} sha256={digest}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE assets
                SET status = 'failed',
                    metadata = metadata || %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (Jsonb({"finalize_error": str(error)[:500]}), asset_id),
            )
        print(f"asset finalization failed: {asset_id}: {error}", flush=True)
    return True


def seed_pending_ingests() -> int:
    with connection() as database:
        result = database.execute(
            """
            INSERT INTO asset_ingests (asset_id, project_id)
            SELECT id, project_id
            FROM assets
            WHERE status = 'ready'
            ON CONFLICT (asset_id) DO NOTHING
            """
        )
        return result.rowcount


def recover_interrupted_ingests() -> int:
    """Requeue work orphaned by the previous instance of this single worker."""

    with connection() as database:
        result = database.execute(
            """
            UPDATE asset_ingests
            SET status = 'pending', lease_expires_at = NULL,
                error = NULL, updated_at = now()
            WHERE status = 'running'
            """
        )
        return result.rowcount


def claim_pending_ingest() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT a.id, a.project_id, a.storage_key, a.mime_type, a.byte_size, a.sha256
            FROM asset_ingests AS ingest
            JOIN assets AS a ON a.id = ingest.asset_id
            WHERE a.status = 'ready'
              AND (
                  ingest.status = 'pending'
                  OR (ingest.status = 'failed' AND ingest.attempts < 3)
                  OR (ingest.status = 'running' AND ingest.lease_expires_at < now())
              )
            ORDER BY ingest.updated_at, ingest.created_at
            LIMIT 1
            FOR UPDATE OF ingest SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        database.execute(
            """
            UPDATE asset_ingests
            SET status = 'running', attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE asset_id = %s
            """,
            (settings.ingest_lease_seconds, row["id"]),
        )
        return row


def analyze_one_asset(state: WorkerState) -> bool:
    asset = claim_pending_ingest()
    if asset is None:
        return False

    asset_id = str(asset["id"])
    state.active_ingest_id = asset_id
    try:
        manifest = analyze_asset(asset)
        with connection() as database:
            database.execute(
                """
                UPDATE asset_ingests
                SET status = 'ready', manifest_path = %s, manifest = %s,
                    lease_expires_at = NULL, completed_at = now(), updated_at = now()
                WHERE asset_id = %s
                """,
                (manifest["manifest_path"], Jsonb(manifest), asset["id"]),
            )
        print(f"asset analysis ready: {asset_id}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE asset_ingests
                SET status = 'failed', error = %s, lease_expires_at = NULL, updated_at = now()
                WHERE asset_id = %s
                """,
                (str(error)[:1000], asset["id"]),
            )
        print(f"asset analysis failed: {asset_id}: {error}", flush=True)
    finally:
        state.active_ingest_id = None
    return True


def recover_interrupted_edits() -> int:
    """Resume an edit from its persisted plan after an abrupt worker stop."""

    with connection() as database:
        result = database.execute(
            """
            UPDATE edit_runs
            SET status = 'pending', lease_expires_at = NULL,
                error = NULL, updated_at = now()
            WHERE status IN ('planning', 'rendering')
            """
        )
        return result.rowcount


def claim_pending_edit() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT edit_runs.*
            FROM edit_runs
            WHERE edit_runs.status = 'pending'
              AND EXISTS (
                  SELECT 1 FROM job_assets WHERE job_assets.job_id = edit_runs.job_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM job_assets
                  JOIN assets ON assets.id = job_assets.asset_id
                  LEFT JOIN asset_ingests ON asset_ingests.asset_id = assets.id
                  WHERE job_assets.job_id = edit_runs.job_id
                    AND (assets.status <> 'ready' OR asset_ingests.status IS DISTINCT FROM 'ready')
              )
            ORDER BY edit_runs.updated_at, edit_runs.created_at
            LIMIT 1
            FOR UPDATE OF edit_runs SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        next_status = "rendering" if row["edit_plan_id"] else "planning"
        claimed = database.execute(
            """
            UPDATE edit_runs
            SET status = %s, attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (next_status, settings.edit_lease_seconds, row["id"]),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = %s, updated_at = now() WHERE id = %s",
            ("planning" if next_status == "planning" else "previewing", row["job_id"]),
        )
        return claimed


def _persist_generated_plan(
    run: dict[str, Any], plan: EditPlan, provenance: dict[str, Any]
) -> str:
    provider = str(provenance["provider"])
    model = str(provenance["model"])
    reasoning_effort = provenance.get("reasoning_effort")
    document = plan.model_dump(mode="json")
    with connection() as database:
        plan_row = database.execute(
            """
            INSERT INTO edit_plans (
                job_id, version, schema_version, document, provider, model, document_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run["job_id"],
                run["version"],
                plan.schema_version,
                Jsonb(document),
                provider,
                model,
                document_sha256(document),
            ),
        ).fetchone()
        database.execute(
            """
            UPDATE edit_runs
            SET status = 'rendering', edit_plan_id = %s, provider = %s, model = %s,
                reasoning_effort = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (plan_row["id"], provider, model, reasoning_effort, run["id"]),
        )
        database.execute(
            "UPDATE jobs SET status = 'previewing', updated_at = now() WHERE id = %s",
            (run["job_id"],),
        )
    return str(plan_row["id"])


def _record_plan_usage(
    run: dict[str, Any], provenance: dict[str, Any], request_kind: str
) -> None:
    usage = provenance.get("usage")
    if not isinstance(usage, dict) or not usage:
        return
    with connection() as database:
        database.execute(
            """
            INSERT INTO ai_usage_events (
                job_id, edit_run_id, provider, model, reasoning_effort,
                request_kind, response_id, input_tokens, cached_input_tokens,
                output_tokens, reasoning_tokens, total_tokens, latency_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run["job_id"],
                run["id"],
                str(provenance["provider"]),
                str(provenance["model"]),
                provenance.get("reasoning_effort"),
                request_kind,
                usage.get("response_id"),
                int(usage.get("input_tokens") or 0),
                int(usage.get("cached_input_tokens") or 0),
                int(usage.get("output_tokens") or 0),
                int(usage.get("reasoning_tokens") or 0),
                int(usage.get("total_tokens") or 0),
                int(usage.get("latency_ms") or 0),
            ),
        )


def process_one_edit(state: WorkerState) -> bool:
    run = claim_pending_edit()
    if run is None:
        return False

    run_id = str(run["id"])
    state.active_edit_run_id = run_id
    try:
        context = build_editor_context(run["job_id"], include_internal_paths=True)
        if not context["ready_for_editing"]:
            raise RuntimeError("source analysis is not ready")

        if run["edit_plan_id"]:
            with connection() as database:
                plan_row = database.execute(
                    "SELECT document, provider, model FROM edit_plans WHERE id = %s",
                    (run["edit_plan_id"],),
                ).fetchone()
            if plan_row is None:
                raise RuntimeError("persisted edit plan was not found")
            plan = validate_edit_plan(
                plan_row["document"],
                context["assets"],
                allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                creative_direction=context["job"],
                music_tracks=context["music_library"],
            )
            provider = str(plan_row["provider"])
            model = str(plan_row["model"])
            reasoning_effort = run.get("reasoning_effort")
        else:
            if run.get("based_on_run_id"):
                with connection() as database:
                    previous = database.execute(
                        """
                        SELECT edit_runs.version, edit_plans.document
                        FROM edit_runs
                        JOIN edit_plans ON edit_plans.id = edit_runs.edit_plan_id
                        WHERE edit_runs.id = %s AND edit_runs.job_id = %s
                        """,
                        (run["based_on_run_id"], run["job_id"]),
                    ).fetchone()
                if previous is None:
                    raise RuntimeError("the revision's previous edit plan was not found")
                context["revision"] = {
                    "instruction": run.get("revision_note") or "",
                    "based_on_version": previous["version"],
                    "previous_plan": previous["document"],
                    "caption_corrections": run.get("caption_corrections") or [],
                }
            proposed, provenance = create_edit_plan(context)
            request_kind = "revision" if run.get("based_on_run_id") else "initial_plan"
            _record_plan_usage(run, provenance, request_kind)
            try:
                plan = validate_edit_plan(
                    proposed.model_dump(mode="json"),
                    context["assets"],
                    allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                )
            except (ValueError, ValidationError) as validation_error:
                if context["project"]["privacy_mode"] == "local_only":
                    raise
                with connection() as database:
                    database.execute(
                        """
                        INSERT INTO job_events (job_id, event_type, payload)
                        VALUES (%s, 'edit_plan_repair_requested', %s)
                        """,
                        (
                            run["job_id"],
                            Jsonb(
                                {
                                    "version": run["version"],
                                    "validation_error": str(validation_error)[:500],
                                }
                            ),
                        ),
                    )
                context["validation_correction"] = {
                    "error": str(validation_error)[:1000],
                    "rejected_plan": proposed.model_dump(mode="json"),
                }
                proposed, provenance = create_edit_plan(context)
                _record_plan_usage(run, provenance, "repair")
                plan = validate_edit_plan(
                    proposed.model_dump(mode="json"),
                    context["assets"],
                    allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                )
            provider = provenance["provider"]
            model = provenance["model"]
            reasoning_effort = provenance.get("reasoning_effort")
            _persist_generated_plan(run, plan, provenance)

        if isinstance(plan, MontageEditPlan):
            manifest = render_montage_preview(
                context,
                plan,
                int(run["version"]),
                provider,
                model,
                list(run.get("caption_corrections") or []),
            )
        else:
            manifest = render_edit_preview(
                context,
                plan,
                int(run["version"]),
                provider,
                model,
                list(run.get("caption_corrections") or []),
            )
        with connection() as database:
            database.execute(
                """
                UPDATE edit_runs
                SET status = 'ready', provider = %s, model = %s, reasoning_effort = %s,
                    preview_path = %s, manifest_path = %s, manifest = %s,
                    lease_expires_at = NULL, completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (
                    provider,
                    model,
                    reasoning_effort,
                    manifest["outputs"]["preview"],
                    manifest["manifest_path"],
                    Jsonb(manifest),
                    run["id"],
                ),
            )
            database.execute(
                "UPDATE jobs SET status = 'awaiting_review', revision = %s, updated_at = now() WHERE id = %s",
                (run["version"], run["job_id"]),
            )
            database.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'preview_ready', %s)",
                (run["job_id"], Jsonb({"version": run["version"], "run_id": run_id})),
            )
        print(f"edit preview ready: {run_id}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE edit_runs
                SET status = 'failed', error = %s, lease_expires_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (str(error)[:1000], run["id"]),
            )
            database.execute(
                "UPDATE jobs SET status = 'failed', updated_at = now() WHERE id = %s",
                (run["job_id"],),
            )
            database.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'preview_failed', %s)",
                (run["job_id"], Jsonb({"version": run["version"], "error": str(error)[:500]})),
            )
        print(f"edit preview failed: {run_id}: {error}", flush=True)
    finally:
        state.active_edit_run_id = None
    return True


def recover_interrupted_final_exports() -> int:
    with connection() as database:
        result = database.execute(
            """
            UPDATE final_exports
            SET status = 'pending', lease_expires_at = NULL,
                error = NULL, updated_at = now()
            WHERE status = 'rendering'
            """
        )
        return result.rowcount


def claim_pending_final_export() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT final_exports.*, edit_runs.version, edit_runs.edit_plan_id,
                   edit_runs.provider, edit_runs.model, edit_runs.caption_corrections,
                   edit_runs.approved_at
            FROM final_exports
            JOIN edit_runs ON edit_runs.id = final_exports.edit_run_id
            WHERE final_exports.status = 'pending'
               OR (final_exports.status = 'failed' AND final_exports.attempts < 3)
               OR (final_exports.status = 'rendering' AND final_exports.lease_expires_at < now())
            ORDER BY final_exports.updated_at, final_exports.created_at
            LIMIT 1
            FOR UPDATE OF final_exports SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        claimed = database.execute(
            """
            UPDATE final_exports
            SET status = 'rendering', attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (settings.edit_lease_seconds, row["id"]),
        ).fetchone()
        database.execute(
            "UPDATE jobs SET status = 'exporting', updated_at = now() WHERE id = %s",
            (row["job_id"],),
        )
        return {**row, **claimed}


def process_one_final_export(state: WorkerState) -> bool:
    export = claim_pending_final_export()
    if export is None:
        return False

    export_id = str(export["id"])
    state.active_final_export_id = export_id
    try:
        with connection() as database:
            plan_row = database.execute(
                "SELECT document FROM edit_plans WHERE id = %s",
                (export["edit_plan_id"],),
            ).fetchone()
        if plan_row is None:
            raise RuntimeError("the approved edit plan was not found")
        context = build_editor_context(export["job_id"], include_internal_paths=True)
        plan = validate_edit_plan(
            plan_row["document"],
            context["assets"],
            allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
            creative_direction=context["job"],
            music_tracks=context["music_library"],
        )
        approved_at = export.get("approved_at")
        if approved_at is None:
            raise RuntimeError("the selected edit version is not approved")
        if isinstance(plan, MontageEditPlan):
            manifest = render_montage_delivery(
                context,
                plan,
                int(export["version"]),
                str(export["provider"]),
                str(export["model"]),
                list(export.get("caption_corrections") or []),
                approved_at.isoformat(),
            )
        else:
            manifest = render_final_delivery(
                context,
                plan,
                int(export["version"]),
                str(export["provider"]),
                str(export["model"]),
                list(export.get("caption_corrections") or []),
                approved_at.isoformat(),
            )
        outputs = manifest["outputs"]
        with connection() as database:
            database.execute(
                """
                UPDATE final_exports
                SET status = 'ready', video_path = %s, captions_path = %s,
                    cover_path = %s, post_copy_path = %s, package_path = %s, manifest_path = %s,
                    manifest = %s, lease_expires_at = NULL,
                    completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (
                    outputs["video"],
                    outputs["captions"],
                    outputs["cover"],
                    outputs.get("post_copy"),
                    outputs["package"],
                    manifest["manifest_path"],
                    Jsonb(manifest),
                    export["id"],
                ),
            )
            database.execute(
                "UPDATE jobs SET status = 'delivered', revision = %s, updated_at = now() WHERE id = %s",
                (export["version"], export["job_id"]),
            )
            database.execute(
                """
                INSERT INTO job_events (job_id, event_type, payload)
                VALUES (%s, 'final_export_ready', %s)
                """,
                (
                    export["job_id"],
                    Jsonb({"version": export["version"], "export_id": export_id}),
                ),
            )
        print(f"final export ready: {export_id}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE final_exports
                SET status = 'failed', error = %s, lease_expires_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (str(error)[:1000], export["id"]),
            )
            database.execute(
                "UPDATE jobs SET status = 'failed', updated_at = now() WHERE id = %s",
                (export["job_id"],),
            )
            database.execute(
                """
                INSERT INTO job_events (job_id, event_type, payload)
                VALUES (%s, 'final_export_failed', %s)
                """,
                (
                    export["job_id"],
                    Jsonb({"version": export["version"], "error": str(error)[:500]}),
                ),
            )
        print(f"final export failed: {export_id}: {error}", flush=True)
    finally:
        state.active_final_export_id = None
    return True


def refresh_editor_model_catalog() -> int:
    settings = get_settings()
    models = list_chatgpt_models(settings)
    with connection() as database:
        database.execute("UPDATE editor_models SET available = false WHERE provider = 'chatgpt_plan'")
        for index, model in enumerate(models):
            database.execute(
                """
                INSERT INTO editor_models (
                    slug, display_name, provider, available, sort_order, refreshed_at
                ) VALUES (%s, %s, 'chatgpt_plan', true, %s, now())
                ON CONFLICT (slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    provider = EXCLUDED.provider,
                    available = true,
                    sort_order = EXCLUDED.sort_order,
                    refreshed_at = now()
                """,
                (model["slug"], model["display_name"], index),
            )
    return len(models)


def analyze_pending_music_tracks() -> int:
    settings = get_settings()
    with connection() as database:
        rows = database.execute(
            """
            SELECT id, storage_key, duration_seconds
            FROM music_tracks
            WHERE active = true
              AND (bpm IS NULL OR jsonb_array_length(beat_grid_seconds) = 0)
            ORDER BY created_at
            """
        ).fetchall()
    completed = 0
    for row in rows:
        try:
            source = resolve_source(settings.media_root, str(row["storage_key"]))
            analysis = analyze_music_beats(
                source,
                float(row["duration_seconds"]),
                settings.analysis_command_timeout_seconds,
            )
            with connection() as database:
                database.execute(
                    """
                    UPDATE music_tracks
                    SET bpm = %s, beat_grid_seconds = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (analysis["bpm"], Jsonb(analysis["beat_grid_seconds"]), row["id"]),
                )
            completed += 1
        except Exception as error:
            print(f"music beat analysis deferred for {row['id']}: {error}", flush=True)
    return completed


def heartbeat_loop(state: WorkerState, stop_event: threading.Event) -> None:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    interval = min(15, max(5, settings.worker_heartbeat_ttl_seconds // 3))
    try:
        while not stop_event.is_set():
            status = (
                "analyzing"
                if state.active_ingest_id
                else "editing"
                if state.active_edit_run_id
                else "exporting"
                if state.active_final_export_id
                else "idle"
            )
            client.set(
                settings.worker_heartbeat_key,
                json.dumps(
                    {
                        "unix_time": time.time(),
                        "status": status,
                        "asset_id": state.active_ingest_id,
                        "edit_run_id": state.active_edit_run_id,
                        "final_export_id": state.active_final_export_id,
                    }
                ),
                ex=settings.worker_heartbeat_ttl_seconds,
            )
            if state.active_ingest_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE asset_ingests
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE asset_id = %s AND status = 'running'
                            """,
                            (settings.ingest_lease_seconds, state.active_ingest_id),
                        )
                except Exception as error:
                    print(f"ingest lease heartbeat failed: {error}", flush=True)
            if state.active_edit_run_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE edit_runs
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE id = %s AND status IN ('planning', 'rendering')
                            """,
                            (settings.edit_lease_seconds, state.active_edit_run_id),
                        )
                except Exception as error:
                    print(f"edit lease heartbeat failed: {error}", flush=True)
            if state.active_final_export_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE final_exports
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE id = %s AND status = 'rendering'
                            """,
                            (settings.edit_lease_seconds, state.active_final_export_id),
                        )
                except Exception as error:
                    print(f"final export lease heartbeat failed: {error}", flush=True)
            stop_event.wait(interval)
    finally:
        client.delete(settings.worker_heartbeat_key)
        client.close()


def main() -> None:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    state = WorkerState()
    heartbeat_stop = threading.Event()

    def stop(_: int, __: object) -> None:
        state.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(state, heartbeat_stop),
        name="worker-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    recovered = recover_interrupted_ingests()
    if recovered:
        print(f"requeued interrupted analyses: {recovered}", flush=True)
    recovered_edits = recover_interrupted_edits()
    if recovered_edits:
        print(f"requeued interrupted edits: {recovered_edits}", flush=True)
    recovered_exports = recover_interrupted_final_exports()
    if recovered_exports:
        print(f"requeued interrupted final exports: {recovered_exports}", flush=True)
    try:
        model_count = refresh_editor_model_catalog()
        print(f"refreshed ChatGPT model catalogue: {model_count} models", flush=True)
    except Exception as error:
        print(f"ChatGPT model catalogue refresh deferred: {error}", flush=True)
    music_count = analyze_pending_music_tracks()
    if music_count:
        print(f"analyzed music beat grids: {music_count}", flush=True)
    next_model_refresh = time.monotonic() + settings.editor_model_refresh_seconds
    print("worker ready", flush=True)
    while not state.stopping:
        if time.monotonic() >= next_model_refresh:
            try:
                model_count = refresh_editor_model_catalog()
                print(f"refreshed ChatGPT model catalogue: {model_count} models", flush=True)
            except Exception as error:
                print(f"ChatGPT model catalogue refresh deferred: {error}", flush=True)
            next_model_refresh = time.monotonic() + settings.editor_model_refresh_seconds
        while finalize_one_upload():
            if state.stopping:
                break
        seed_pending_ingests()
        while not state.stopping and analyze_one_asset(state):
            seed_pending_ingests()
        while not state.stopping and process_one_edit(state):
            pass
        while not state.stopping and process_one_final_export(state):
            pass
        # Redis is a wake-up channel. PostgreSQL remains the durable source of
        # truth, so a lost queue notification cannot strand an uploaded asset.
        item = client.blpop(settings.worker_queue, timeout=5)
        if item is not None:
            _, payload = item
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                message = {}
            if message.get("type") != "finalize_upload":
                print(f"deferred unsupported job payload: {payload[:200]}", flush=True)

    heartbeat_stop.set()
    heartbeat_thread.join(timeout=10)
    client.close()
    print("worker stopped", flush=True)


if __name__ == "__main__":
    main()
