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
from app.content_catalog import CATALOG_VERSION, build_catalog_segments
from app.database import connection
from app.duplicate_storage import share_exact_duplicate_storage
from app.edit_plan import (
    EditPlan,
    MontageEditPlan,
    apply_timeline_adjustments,
    derive_duration_variant,
    document_sha256,
    repair_predictable_plan_defaults,
    validate_edit_plan,
)
from app.edit_renderer import render_edit_preview, render_final_delivery
from app.editor_context import build_editor_context
from app.editor_provider import create_edit_plan, list_chatgpt_models
from app.finalize_upload import finalize_original, upload_source_path
from app.media_analysis import analyze_asset, resolve_source
from app.productization import assert_ai_budget
from app.story_intelligence import STORY_INTELLIGENCE_VERSION, build_story_moments
from app.take_quality import editing_policy
from app.montage_renderer import render_montage_delivery, render_montage_preview
from app.music_analysis import analyze_music_beats
from app.revision_report import compare_revision
from app.visual_index import (
    VISUAL_INDEX_VERSION,
    VISUAL_MODEL_ID,
    VISUAL_MODEL_REVISION,
    VISUAL_VECTOR_DIMENSION,
    build_visual_frames,
    canonical_assignments,
    embed_frame_paths,
)


@dataclass
class WorkerState:
    stopping: bool = False
    active_ingest_id: str | None = None
    active_catalog_id: str | None = None
    active_visual_index_id: str | None = None
    active_edit_run_id: str | None = None
    active_final_export_id: str | None = None
    active_delivery_variant_id: str | None = None


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
            canonical = database.execute(
                """
                SELECT existing.id, existing.storage_key
                FROM assets AS existing
                LEFT JOIN asset_duplicate_reviews
                  ON asset_duplicate_reviews.sha256 = existing.sha256
                 AND asset_duplicate_reviews.canonical_asset_id = existing.id
                WHERE existing.id <> %s
                  AND existing.sha256 = %s
                  AND existing.byte_size = %s
                  AND existing.status = 'ready'
                ORDER BY asset_duplicate_reviews.canonical_asset_id IS NOT NULL DESC,
                         existing.created_at, existing.id
                LIMIT 1
                """,
                (asset_id, digest, int(asset["byte_size"])),
            ).fetchone()
            if canonical is not None:
                canonical_path = resolve_source(settings.media_root, str(canonical["storage_key"]))
                try:
                    shared = share_exact_duplicate_storage(
                        canonical_path,
                        destination,
                        expected_sha256=digest,
                        expected_size=int(asset["byte_size"]),
                    )
                    database.execute(
                        """
                        INSERT INTO asset_storage_optimizations (
                            asset_id, canonical_asset_id, sha256, bytes_reclaimed,
                            source_storage_key, canonical_storage_key,
                            device, inode, reason
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'upload_exact_match')
                        ON CONFLICT (asset_id) DO NOTHING
                        """,
                        (
                            asset_id,
                            canonical["id"],
                            digest,
                            shared.bytes_reclaimed,
                            relative_path,
                            canonical["storage_key"],
                            shared.device,
                            shared.inode,
                        ),
                    )
                    print(
                        f"asset storage reused: {asset_id} shares verified bytes with {canonical['id']}",
                        flush=True,
                    )
                except (OSError, ValueError) as optimization_error:
                    # Storage reuse is an optimization. The new write-once
                    # original remains valid when the filesystem cannot share it.
                    print(
                        f"asset storage reuse skipped: {asset_id}: {optimization_error}",
                        flush=True,
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
            database.execute(
                """
                INSERT INTO asset_catalogs (asset_id, status, attempts, error, updated_at)
                VALUES (%s, 'pending', 0, NULL, now())
                ON CONFLICT (asset_id) DO UPDATE SET
                    status = 'pending', attempts = 0, lease_expires_at = NULL,
                    error = NULL, completed_at = NULL, updated_at = now()
                """,
                (asset["id"],),
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


def seed_pending_catalogs() -> int:
    with connection() as database:
        inserted = database.execute(
            """
            INSERT INTO asset_catalogs (asset_id, status)
            SELECT asset_ingests.asset_id, 'pending'
            FROM asset_ingests
            JOIN assets ON assets.id = asset_ingests.asset_id
            WHERE asset_ingests.status = 'ready'
              AND assets.status = 'ready'
            ON CONFLICT (asset_id) DO NOTHING
            """
        )
        refreshed = database.execute(
            """
            UPDATE asset_catalogs
            SET status = 'pending', attempts = 0, lease_expires_at = NULL,
                error = NULL, completed_at = NULL, updated_at = now()
            WHERE catalog_version <> %s
              AND status <> 'running'
            """,
            (CATALOG_VERSION,),
        )
        return inserted.rowcount + refreshed.rowcount


def recover_interrupted_catalogs() -> int:
    with connection() as database:
        result = database.execute(
            """
            UPDATE asset_catalogs
            SET status = 'pending', lease_expires_at = NULL,
                error = NULL, updated_at = now()
            WHERE status = 'running'
            """
        )
        return result.rowcount


def claim_pending_catalog() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT assets.id, assets.project_id, assets.source_name,
                   assets.mime_type, assets.byte_size, assets.sha256,
                   asset_ingests.manifest
            FROM asset_catalogs
            JOIN assets ON assets.id = asset_catalogs.asset_id
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.status = 'ready'
              AND asset_ingests.status = 'ready'
              AND (
                  asset_catalogs.status = 'pending'
                  OR (asset_catalogs.status = 'failed' AND asset_catalogs.attempts < 3)
                  OR (
                      asset_catalogs.status = 'running'
                      AND asset_catalogs.lease_expires_at < now()
                  )
              )
            ORDER BY asset_catalogs.updated_at, asset_catalogs.created_at
            LIMIT 1
            FOR UPDATE OF asset_catalogs SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        database.execute(
            """
            UPDATE asset_catalogs
            SET status = 'running', attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()),
                updated_at = now()
            WHERE asset_id = %s
            """,
            (settings.ingest_lease_seconds, row["id"]),
        )
        return row


def catalog_one_asset(state: WorkerState) -> bool:
    asset = claim_pending_catalog()
    if asset is None:
        return False
    asset_id = str(asset["id"])
    state.active_catalog_id = asset_id
    try:
        manifest = asset.get("manifest") if isinstance(asset.get("manifest"), dict) else {}
        segments = build_catalog_segments(asset, manifest)
        story_moments = build_story_moments(asset, manifest)
        transcript_count = sum(segment["segment_kind"] == "transcript" for segment in segments)
        scene_count = sum(segment["segment_kind"] == "scene" for segment in segments)
        with connection() as database:
            database.execute(
                "DELETE FROM asset_catalog_segments WHERE asset_id = %s",
                (asset["id"],),
            )
            for segment in segments:
                database.execute(
                    """
                    INSERT INTO asset_catalog_segments (
                        asset_id, project_id, segment_kind, segment_index,
                        start_seconds, end_seconds, text, facts,
                        source_model, catalog_version
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        asset["id"],
                        asset["project_id"],
                        segment["segment_kind"],
                        segment["segment_index"],
                        segment["start_seconds"],
                        segment["end_seconds"],
                        segment["text"],
                        Jsonb(segment["facts"]),
                        segment["source_model"],
                        CATALOG_VERSION,
                    ),
                )
            database.execute(
                """
                INSERT INTO asset_story_indexes (
                    asset_id, status, story_version, moment_count, moments,
                    error, completed_at, updated_at
                )
                VALUES (%s, 'ready', %s, %s, %s, NULL, now(), now())
                ON CONFLICT (asset_id) DO UPDATE SET
                    status = 'ready', story_version = EXCLUDED.story_version,
                    moment_count = EXCLUDED.moment_count, moments = EXCLUDED.moments,
                    error = NULL, completed_at = now(), updated_at = now()
                """,
                (
                    asset["id"],
                    STORY_INTELLIGENCE_VERSION,
                    len(story_moments),
                    Jsonb(story_moments),
                ),
            )
            database.execute(
                """
                UPDATE asset_catalogs
                SET status = 'ready', catalog_version = %s,
                    segment_count = %s, transcript_segment_count = %s,
                    scene_segment_count = %s, lease_expires_at = NULL,
                    error = NULL, completed_at = now(), updated_at = now()
                WHERE asset_id = %s
                """,
                (
                    CATALOG_VERSION,
                    len(segments),
                    transcript_count,
                    scene_count,
                    asset["id"],
                ),
            )
        print(f"asset catalogue ready: {asset_id} segments={len(segments)}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                INSERT INTO asset_story_indexes (asset_id, status, error, updated_at)
                VALUES (%s, 'failed', %s, now())
                ON CONFLICT (asset_id) DO UPDATE SET
                    status = 'failed', error = EXCLUDED.error, updated_at = now()
                """,
                (asset["id"], str(error)[:1000]),
            )
            database.execute(
                """
                UPDATE asset_catalogs
                SET status = 'failed', error = %s, lease_expires_at = NULL,
                    updated_at = now()
                WHERE asset_id = %s
                """,
                (str(error)[:1000], asset["id"]),
            )
        print(f"asset catalogue failed: {asset_id}: {error}", flush=True)
    finally:
        state.active_catalog_id = None
    return True


def seed_pending_visual_indexes() -> int:
    """Reconcile canonical duplicate choices and queue missing/current-model indexes."""

    changed = 0
    with connection() as database:
        eligible = database.execute(
            """
            SELECT assets.id, assets.sha256
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            JOIN asset_catalogs ON asset_catalogs.asset_id = assets.id
            WHERE assets.status = 'ready'
              AND assets.library_status = 'active'
              AND asset_ingests.status = 'ready'
              AND asset_catalogs.status = 'ready'
              AND (assets.mime_type LIKE 'video/%' OR assets.mime_type LIKE 'image/%')
            ORDER BY assets.created_at, assets.id
            """
        ).fetchall()
        reviews = database.execute(
            """
            SELECT sha256, canonical_asset_id, asset_count
            FROM asset_duplicate_reviews
            """
        ).fetchall()
        current_rows = database.execute(
            """
            SELECT asset_id, canonical_asset_id, status, model_id,
                   model_revision, index_version
            FROM asset_visual_indexes
            """
        ).fetchall()
        current = {row["asset_id"]: row for row in current_rows}
        assignments = canonical_assignments(list(eligible), list(reviews))

        for row in eligible:
            asset_id = row["id"]
            canonical_id = assignments[asset_id]
            existing = current.get(asset_id)
            is_alias = asset_id != canonical_id
            needs_refresh = bool(
                existing is None
                or existing["canonical_asset_id"] != canonical_id
                or existing["model_id"] != VISUAL_MODEL_ID
                or existing["model_revision"] != VISUAL_MODEL_REVISION
                or existing["index_version"] != VISUAL_INDEX_VERSION
                or (not is_alias and existing["status"] == "aliased")
            )
            if existing is None:
                database.execute(
                    """
                    INSERT INTO asset_visual_indexes (
                        asset_id, canonical_asset_id, status, model_id,
                        model_revision, index_version, vector_dimension
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        asset_id,
                        canonical_id,
                        "aliased" if is_alias else "pending",
                        VISUAL_MODEL_ID,
                        VISUAL_MODEL_REVISION,
                        VISUAL_INDEX_VERSION,
                        VISUAL_VECTOR_DIMENSION,
                    ),
                )
                changed += 1
            elif needs_refresh or (is_alias and existing["status"] != "aliased"):
                next_status = "aliased" if is_alias else "pending"
                database.execute(
                    """
                    UPDATE asset_visual_indexes
                    SET canonical_asset_id = %s, status = %s, attempts = 0,
                        lease_expires_at = NULL, model_id = %s,
                        model_revision = %s, index_version = %s,
                        vector_dimension = %s, frame_count = 0, error = NULL,
                        completed_at = NULL, updated_at = now()
                    WHERE asset_id = %s
                    """,
                    (
                        canonical_id,
                        next_status,
                        VISUAL_MODEL_ID,
                        VISUAL_MODEL_REVISION,
                        VISUAL_INDEX_VERSION,
                        VISUAL_VECTOR_DIMENSION,
                        asset_id,
                    ),
                )
                database.execute(
                    "DELETE FROM asset_visual_embeddings WHERE asset_id = %s",
                    (asset_id,),
                )
                changed += 1
    return changed


def recover_interrupted_visual_indexes() -> int:
    with connection() as database:
        result = database.execute(
            """
            UPDATE asset_visual_indexes
            SET status = 'pending', lease_expires_at = NULL,
                error = NULL, updated_at = now()
            WHERE status = 'running'
            """
        )
        return result.rowcount


def claim_pending_visual_index() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT assets.id, assets.project_id, assets.storage_key,
                   assets.source_name, assets.mime_type
            FROM asset_visual_indexes
            JOIN assets ON assets.id = asset_visual_indexes.asset_id
            WHERE asset_visual_indexes.canonical_asset_id = assets.id
              AND (
                  asset_visual_indexes.status = 'pending'
                  OR (
                      asset_visual_indexes.status = 'failed'
                      AND asset_visual_indexes.attempts < 3
                  )
                  OR (
                      asset_visual_indexes.status = 'running'
                      AND asset_visual_indexes.lease_expires_at < now()
                  )
              )
            ORDER BY asset_visual_indexes.updated_at, asset_visual_indexes.created_at
            LIMIT 1
            FOR UPDATE OF asset_visual_indexes SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        database.execute(
            """
            UPDATE asset_visual_indexes
            SET status = 'running', attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()),
                updated_at = now()
            WHERE asset_id = %s
            """,
            (settings.ingest_lease_seconds, row["id"]),
        )
        return row


def index_one_asset_visually(state: WorkerState) -> bool:
    asset = claim_pending_visual_index()
    if asset is None:
        return False
    asset_id = str(asset["id"])
    state.active_visual_index_id = asset_id
    try:
        with connection() as database:
            segments = database.execute(
                """
                SELECT segment_kind, segment_index, start_seconds, end_seconds
                FROM asset_catalog_segments
                WHERE asset_id = %s AND segment_kind IN ('scene', 'image')
                ORDER BY segment_kind, segment_index
                """,
                (asset["id"],),
            ).fetchall()
        if not segments:
            raise RuntimeError("the asset has no visual catalogue segments")
        frames = build_visual_frames(asset, list(segments))
        embeddings: list[list[float]] = []
        for offset in range(0, len(frames), 16):
            batch = frames[offset:offset + 16]
            embeddings.extend(embed_frame_paths([frame["frame_path"] for frame in batch]))
        if len(embeddings) != len(frames):
            raise RuntimeError("visual encoder returned the wrong number of embeddings")

        with connection() as database:
            database.execute(
                "DELETE FROM asset_visual_embeddings WHERE asset_id = %s",
                (asset["id"],),
            )
            for frame, embedding in zip(frames, embeddings):
                database.execute(
                    """
                    INSERT INTO asset_visual_embeddings (
                        asset_id, project_id, segment_kind, segment_index,
                        frame_index, start_seconds, end_seconds, frame_seconds,
                        frame_path, embedding, source_model, model_revision,
                        index_version
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s::real[], %s, %s, %s
                    )
                    """,
                    (
                        asset["id"],
                        asset["project_id"],
                        frame["segment_kind"],
                        frame["segment_index"],
                        frame["frame_index"],
                        frame["start_seconds"],
                        frame["end_seconds"],
                        frame["frame_seconds"],
                        frame["frame_path"],
                        embedding,
                        VISUAL_MODEL_ID,
                        VISUAL_MODEL_REVISION,
                        VISUAL_INDEX_VERSION,
                    ),
                )
            database.execute(
                """
                UPDATE asset_visual_indexes
                SET status = 'ready', canonical_asset_id = asset_id,
                    model_id = %s, model_revision = %s, index_version = %s,
                    vector_dimension = %s, frame_count = %s,
                    lease_expires_at = NULL, error = NULL,
                    completed_at = now(), updated_at = now()
                WHERE asset_id = %s
                """,
                (
                    VISUAL_MODEL_ID,
                    VISUAL_MODEL_REVISION,
                    VISUAL_INDEX_VERSION,
                    VISUAL_VECTOR_DIMENSION,
                    len(frames),
                    asset["id"],
                ),
            )
        print(f"visual index ready: {asset_id} frames={len(frames)}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE asset_visual_indexes
                SET status = 'failed', error = %s, lease_expires_at = NULL,
                    updated_at = now()
                WHERE asset_id = %s
                """,
                (str(error)[:1000], asset["id"]),
            )
        print(f"visual index failed: {asset_id}: {error}", flush=True)
    finally:
        state.active_visual_index_id = None
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
            persisted_document, persisted_repairs = repair_predictable_plan_defaults(
                plan_row["document"],
                creative_direction=context["job"],
                music_tracks=context["music_library"],
                creative_effects=context["creative_effect_library"],
            )
            plan = validate_edit_plan(
                persisted_document,
                context["assets"],
                allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                creative_direction=context["job"],
                music_tracks=context["music_library"],
                creative_effects=context["creative_effect_library"],
            )
            if persisted_repairs:
                with connection() as database:
                    database.execute(
                        """
                        INSERT INTO job_events (job_id, event_type, payload)
                        VALUES (%s, 'edit_plan_repaired_deterministically', %s)
                        """,
                        (
                            run["job_id"],
                            Jsonb(
                                {
                                    "version": run["version"],
                                    "repairs": persisted_repairs,
                                    "reused_plan": True,
                                }
                            ),
                        ),
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
                    "mode": run.get("revision_mode") or "targeted",
                    "based_on_version": previous["version"],
                    "previous_plan": previous["document"],
                    "caption_corrections": run.get("caption_corrections") or [],
                    "locked_elements": run.get("locked_elements") or [],
                }
                context["job"]["editorial_policy"] = editing_policy({
                    **context["job"], "project_name": context["project"]["name"],
                    "brief": context["project"]["brief"] + " " + str(run.get("revision_note") or ""),
                })
            adjustments = list(run.get("clip_adjustments") or [])
            deterministic_revision = bool(run.get("based_on_run_id")) and not run.get("revision_note")
            if deterministic_revision:
                previous_document, _ = repair_predictable_plan_defaults(
                    context["revision"]["previous_plan"],
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                    creative_effects=context["creative_effect_library"],
                )
                previous_plan = validate_edit_plan(
                    previous_document,
                    context["assets"],
                    allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                    creative_effects=context["creative_effect_library"],
                )
                proposed = (
                    apply_timeline_adjustments(previous_plan, adjustments, context["assets"])
                    if adjustments
                    else previous_plan
                )
                caption_settings = dict(run.get("caption_settings") or {})
                if caption_settings:
                    proposed = proposed.model_copy(
                        update={
                            "caption_position": caption_settings.get(
                                "position", proposed.caption_position
                            ),
                            "caption_timing_offset_seconds": caption_settings.get(
                                "timing_offset_seconds",
                                proposed.caption_timing_offset_seconds,
                            ),
                        },
                        deep=True,
                    )
                if run.get("effects_enabled") is False:
                    proposed = proposed.model_copy(update={"effects": []}, deep=True)
                provenance = {
                    "provider": (
                        "local_timeline"
                        if adjustments
                        else "local_caption_layout"
                        if caption_settings
                        else "local_effect_controls"
                        if run.get("effects_enabled") is False
                        else "local_caption"
                    ),
                    "model": "deterministic_editor_v1",
                    "reasoning_effort": None,
                }
            else:
                assert_ai_budget()
                proposed, provenance = create_edit_plan(context)
            request_kind = "revision" if run.get("based_on_run_id") else "initial_plan"
            _record_plan_usage(run, provenance, request_kind)
            revision_text = str(run.get("revision_note") or "").lower()
            check_story = context["project"]["privacy_mode"] != "local_only" and not deterministic_revision and (
                not run.get("based_on_run_id") or run.get("revision_mode") == "rebuild_story"
                or any(term in revision_text for term in ("blooper", "outtake", "dead space", "dead air", "pause", "story", "retake"))
            ) and "spoken phrases" not in (run.get("locked_elements") or [])
            try:
                plan = validate_edit_plan(
                    proposed.model_dump(mode="json"),
                    context["assets"],
                    allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                    creative_effects=context["creative_effect_library"],
                    enforce_story_quality=check_story,
                )
            except (ValueError, ValidationError) as validation_error:
                if context["project"]["privacy_mode"] == "local_only":
                    raise
                repaired_document, deterministic_repairs = repair_predictable_plan_defaults(
                    proposed.model_dump(mode="json"),
                    creative_direction=context["job"],
                    music_tracks=context["music_library"],
                    creative_effects=context["creative_effect_library"],
                    previous_plan=(context.get("revision") or {}).get("previous_plan"),
                    complete_creative_defaults=not deterministic_revision,
                )
                try:
                    if not deterministic_repairs:
                        raise validation_error
                    plan = validate_edit_plan(
                        repaired_document,
                        context["assets"],
                        allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                        creative_direction=context["job"],
                        music_tracks=context["music_library"],
                        creative_effects=context["creative_effect_library"],
                        enforce_story_quality=check_story,
                    )
                except (ValueError, ValidationError) as deterministic_error:
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
                        "error": str(deterministic_error)[:1000],
                        "rejected_plan": repaired_document,
                    }
                    assert_ai_budget()
                    proposed, provenance = create_edit_plan(context)
                    _record_plan_usage(run, provenance, "repair")
                    final_document, final_repairs = repair_predictable_plan_defaults(
                        proposed.model_dump(mode="json"),
                        creative_direction=context["job"],
                        music_tracks=context["music_library"],
                        creative_effects=context["creative_effect_library"],
                        previous_plan=(context.get("revision") or {}).get("previous_plan"),
                        complete_creative_defaults=True,
                    )
                    plan = validate_edit_plan(
                        final_document,
                        context["assets"],
                        allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
                        creative_direction=context["job"],
                        music_tracks=context["music_library"],
                        creative_effects=context["creative_effect_library"],
                        enforce_story_quality=check_story,
                    )
                    deterministic_repairs.extend(final_repairs)
                else:
                    with connection() as database:
                        database.execute(
                            """
                            INSERT INTO job_events (job_id, event_type, payload)
                            VALUES (%s, 'edit_plan_repaired_deterministically', %s)
                            """,
                            (
                                run["job_id"],
                                Jsonb(
                                    {
                                        "version": run["version"],
                                        "repairs": deterministic_repairs,
                                    }
                                ),
                            ),
                        )
            provider = provenance["provider"]
            model = provenance["model"]
            reasoning_effort = provenance.get("reasoning_effort")
            _persist_generated_plan(run, plan, provenance)

        if run.get("based_on_run_id"):
            with connection() as database:
                prior = database.execute(
                    """SELECT document, caption_corrections FROM edit_plans JOIN edit_runs
                       ON edit_runs.edit_plan_id = edit_plans.id
                       WHERE edit_runs.id = %s AND edit_runs.job_id = %s""",
                    (run["based_on_run_id"], run["job_id"]),
                ).fetchone()
            if prior is not None:
                context["revision_report"] = compare_revision(
                    prior["document"], plan.model_dump(mode="json")
                )
                context["revision_report"]["mode"] = run.get("revision_mode") or "targeted"
                context["revision_report"]["instruction"] = run.get("revision_note") or ""
                if (run.get("caption_corrections") or []) != (prior.get("caption_corrections") or []):
                    context["revision_report"]["changes"].append("Caption text corrections changed.")
                    context["revision_report"]["changed"] = True
                    context["revision_report"]["notice"] = ""

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
        render_document, _ = repair_predictable_plan_defaults(
            plan_row["document"],
            creative_direction=context["job"],
            music_tracks=context["music_library"],
            creative_effects=context["creative_effect_library"],
        )
        plan = validate_edit_plan(
            render_document,
            context["assets"],
            allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
            creative_direction=context["job"],
            music_tracks=context["music_library"],
            creative_effects=context["creative_effect_library"],
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


def recover_interrupted_delivery_variants() -> int:
    with connection() as database:
        result = database.execute(
            """
            UPDATE delivery_variants
            SET status = 'pending', lease_expires_at = NULL, error = NULL, updated_at = now()
            WHERE status = 'rendering'
            """
        )
        return result.rowcount


def claim_pending_delivery_variant() -> dict[str, Any] | None:
    settings = get_settings()
    with connection() as database:
        row = database.execute(
            """
            SELECT delivery_variants.*, edit_runs.version, edit_runs.edit_plan_id,
                   edit_runs.provider, edit_runs.model, edit_runs.caption_corrections,
                   edit_runs.approved_at
            FROM delivery_variants
            JOIN edit_runs ON edit_runs.id = delivery_variants.edit_run_id
            WHERE delivery_variants.status = 'pending'
               OR (delivery_variants.status = 'failed' AND delivery_variants.attempts < 3)
               OR (delivery_variants.status = 'rendering' AND delivery_variants.lease_expires_at < now())
            ORDER BY delivery_variants.updated_at, delivery_variants.created_at
            LIMIT 1
            FOR UPDATE OF delivery_variants SKIP LOCKED
            """
        ).fetchone()
        if row is None:
            return None
        claimed = database.execute(
            """
            UPDATE delivery_variants
            SET status = 'rendering', attempts = attempts + 1,
                lease_expires_at = now() + (%s * interval '1 second'),
                error = NULL, started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (settings.edit_lease_seconds, row["id"]),
        ).fetchone()
        return {**row, **claimed}


def process_one_delivery_variant(state: WorkerState) -> bool:
    variant = claim_pending_delivery_variant()
    if variant is None:
        return False
    variant_id = str(variant["id"])
    state.active_delivery_variant_id = variant_id
    try:
        with connection() as database:
            plan_row = database.execute(
                "SELECT document FROM edit_plans WHERE id = %s",
                (variant["edit_plan_id"],),
            ).fetchone()
        if plan_row is None:
            raise RuntimeError("the approved edit plan was not found")
        context = build_editor_context(variant["job_id"], include_internal_paths=True)
        render_document, _ = repair_predictable_plan_defaults(
            plan_row["document"],
            creative_direction=context["job"],
            music_tracks=context["music_library"],
            creative_effects=context["creative_effect_library"],
        )
        plan = validate_edit_plan(
            render_document,
            context["assets"],
            allow_post_copy=bool(context["project"]["ai_copy_allowed"]),
            creative_direction=context["job"],
            music_tracks=context["music_library"],
            creative_effects=context["creative_effect_library"],
        )
        plan = derive_duration_variant(plan, int(variant["target_duration_seconds"]))
        context["job"] = {
            **context["job"],
            "output_aspect": variant["output_aspect"],
            "target_duration_seconds": variant["target_duration_seconds"],
        }
        approved_at = variant.get("approved_at")
        if approved_at is None:
            raise RuntimeError("the selected edit version is not approved")
        slug = f"{variant['output_aspect']}-{variant['target_duration_seconds']}s-{variant_id[:8]}"
        arguments = (
            context,
            plan,
            int(variant["version"]),
            str(variant["provider"]),
            str(variant["model"]),
            list(variant.get("caption_corrections") or []),
            approved_at.isoformat(),
        )
        variant_metadata = {
            "id": variant_id,
            "derived_without_model_call": True,
            "output_aspect": variant["output_aspect"],
            "target_duration_seconds": variant["target_duration_seconds"],
        }
        if isinstance(plan, MontageEditPlan):
            manifest = render_montage_delivery(
                *arguments, delivery_slug=slug, variant_metadata=variant_metadata
            )
        else:
            manifest = render_final_delivery(
                *arguments, delivery_slug=slug, variant_metadata=variant_metadata
            )
        outputs = manifest["outputs"]
        with connection() as database:
            database.execute(
                """
                UPDATE delivery_variants
                SET status = 'ready', video_path = %s, captions_path = %s,
                    cover_path = %s, post_copy_path = %s, package_path = %s,
                    manifest_path = %s, manifest = %s, lease_expires_at = NULL,
                    completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (
                    outputs["video"], outputs["captions"], outputs["cover"],
                    outputs.get("post_copy"), outputs["package"], manifest["manifest_path"],
                    Jsonb(manifest), variant["id"],
                ),
            )
            database.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'delivery_variant_ready', %s)",
                (
                    variant["job_id"],
                    Jsonb(
                        {
                            "variant_id": variant_id,
                            "output_aspect": variant["output_aspect"],
                            "target_duration_seconds": variant["target_duration_seconds"],
                            "model_requests": 0,
                        }
                    ),
                ),
            )
        print(f"delivery variant ready: {variant_id}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute(
                """
                UPDATE delivery_variants
                SET status = 'failed', error = %s, lease_expires_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (str(error)[:1000], variant["id"]),
            )
            database.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'delivery_variant_failed', %s)",
                (variant["job_id"], Jsonb({"variant_id": variant_id, "error": str(error)[:500]})),
            )
        print(f"delivery variant failed: {variant_id}: {error}", flush=True)
    finally:
        state.active_delivery_variant_id = None
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
                else "cataloging"
                if state.active_catalog_id
                else "visual-indexing"
                if state.active_visual_index_id
                else "editing"
                if state.active_edit_run_id
                else "exporting"
                if state.active_final_export_id
                else "rendering-variant"
                if state.active_delivery_variant_id
                else "idle"
            )
            client.set(
                settings.worker_heartbeat_key,
                json.dumps(
                    {
                        "unix_time": time.time(),
                        "status": status,
                        "asset_id": state.active_ingest_id,
                        "catalog_asset_id": state.active_catalog_id,
                        "visual_index_asset_id": state.active_visual_index_id,
                        "edit_run_id": state.active_edit_run_id,
                        "final_export_id": state.active_final_export_id,
                        "delivery_variant_id": state.active_delivery_variant_id,
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
            if state.active_catalog_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE asset_catalogs
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE asset_id = %s AND status = 'running'
                            """,
                            (settings.ingest_lease_seconds, state.active_catalog_id),
                        )
                except Exception as error:
                    print(f"catalogue lease heartbeat failed: {error}", flush=True)
            if state.active_visual_index_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE asset_visual_indexes
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE asset_id = %s AND status = 'running'
                            """,
                            (settings.ingest_lease_seconds, state.active_visual_index_id),
                        )
                except Exception as error:
                    print(f"visual index lease heartbeat failed: {error}", flush=True)
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
            if state.active_delivery_variant_id:
                try:
                    with connection() as database:
                        database.execute(
                            """
                            UPDATE delivery_variants
                            SET lease_expires_at = now() + (%s * interval '1 second'),
                                updated_at = now()
                            WHERE id = %s AND status = 'rendering'
                            """,
                            (settings.edit_lease_seconds, state.active_delivery_variant_id),
                        )
                except Exception as error:
                    print(f"delivery variant lease heartbeat failed: {error}", flush=True)
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
    recovered_catalogs = recover_interrupted_catalogs()
    if recovered_catalogs:
        print(f"requeued interrupted catalogues: {recovered_catalogs}", flush=True)
    recovered_visual_indexes = recover_interrupted_visual_indexes()
    if recovered_visual_indexes:
        print(f"requeued interrupted visual indexes: {recovered_visual_indexes}", flush=True)
    recovered_edits = recover_interrupted_edits()
    if recovered_edits:
        print(f"requeued interrupted edits: {recovered_edits}", flush=True)
    recovered_exports = recover_interrupted_final_exports()
    if recovered_exports:
        print(f"requeued interrupted final exports: {recovered_exports}", flush=True)
    recovered_variants = recover_interrupted_delivery_variants()
    if recovered_variants:
        print(f"requeued interrupted delivery variants: {recovered_variants}", flush=True)
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
        seed_pending_catalogs()
        while not state.stopping and catalog_one_asset(state):
            seed_pending_catalogs()
        while not state.stopping and process_one_edit(state):
            pass
        while not state.stopping and process_one_final_export(state):
            pass
        while not state.stopping and process_one_delivery_variant(state):
            pass
        # Visual backfill is deliberately one asset per loop so an existing
        # library cannot starve user-requested previews or final exports.
        seed_pending_visual_indexes()
        if not state.stopping:
            index_one_asset_visually(state)
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
