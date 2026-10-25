import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from app.config import get_settings
from app.database import connection
from app.duplicate_storage import share_exact_duplicate_storage
from app.schemas import (
    AssetAnalysisResponse,
    AssetCreate,
    AssetResponse,
    CatalogSearchResponse,
    CatalogStatusResponse,
    DuplicateAuditResponse,
    DuplicateCleanupCreate,
    DuplicateCleanupResponse,
    DuplicateReviewCreate,
    DuplicateReviewResponse,
    EditorModelResponse,
    JobAssetAttach,
    JobAssetAttachResponse,
    JobCreate,
    JobResponse,
    LibraryAssetResponse,
    MusicTrackResponse,
    ProjectCreate,
    ProjectResponse,
    VisualIndexStatusResponse,
    VisualReindexResponse,
)
from app.media_analysis import resolve_source
from app.productization import actor_login
from app.visual_index import (
    VISUAL_INDEX_VERSION,
    VISUAL_MODEL_ID,
    VISUAL_MODEL_REVISION,
    embed_text,
    normalized_dot,
    select_visual_matches,
)


router = APIRouter(prefix="/api/v1", tags=["projects"])

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_RECOMMENDATION = (
    "Recommended because it has the most job references; ties prefer the oldest verified original."
)


def _media_kind(mime_type: str) -> Literal["video", "image", "audio"]:
    family = mime_type.split("/", 1)[0]
    if family not in {"video", "image", "audio"}:
        raise ValueError("unsupported library media family")
    return cast(Literal["video", "image", "audio"], family)


def _duplicate_audit(
    asset_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    *,
    originals_scanned: int | None = None,
    query: str = "",
    review_state: Literal["all", "unreviewed", "reviewed"] = "all",
    sort: Literal["most_storage", "most_copies", "newest"] = "most_storage",
    limit: int = 100,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in asset_rows:
        grouped[str(row["sha256"])].append(row)
    reviews = {str(row["sha256"]): row for row in review_rows}

    all_groups: list[dict[str, Any]] = []
    for sha256, copies in grouped.items():
        if len(copies) < 2:
            continue
        ordered = sorted(
            copies,
            key=lambda item: (
                -int(item["job_references"]),
                item["created_at"],
                str(item["id"]),
            ),
        )
        review = reviews.get(sha256)
        reviewed = bool(
            review
            and int(review["asset_count"]) == len(copies)
            and any(copy["id"] == review["canonical_asset_id"] for copy in copies)
        )
        canonical_asset_id = review["canonical_asset_id"] if reviewed else ordered[0]["id"]
        canonical = next(copy for copy in copies if copy["id"] == canonical_asset_id)
        for copy in ordered:
            copy["storage_optimized"] = bool(copy.get("storage_optimized", False))
        unoptimized_copies = [
            copy
            for copy in copies
            if copy["id"] != canonical_asset_id and not copy["storage_optimized"]
        ]
        group = {
            "sha256": sha256,
            "media_kind": _media_kind(str(canonical["mime_type"])),
            "mime_type": canonical["mime_type"],
            "byte_size": int(canonical["byte_size"]),
            "copy_count": len(copies),
            "reclaimable_bytes": sum(int(copy["byte_size"]) for copy in unoptimized_copies),
            "canonical_asset_id": canonical_asset_id,
            "canonical_reason": (
                "Canonical record confirmed during a read-only duplicate review."
                if reviewed
                else CANONICAL_RECOMMENDATION
            ),
            "reviewed": reviewed,
            "reviewed_at": review["reviewed_at"] if reviewed else None,
            "cleanup_ready": reviewed and bool(unoptimized_copies),
            "optimized_copies": sum(
                copy["id"] != canonical_asset_id and copy["storage_optimized"]
                for copy in copies
            ),
            "copies": ordered,
            "_newest": max(copy["created_at"] for copy in copies),
        }
        all_groups.append(group)

    summary = {
        "originals_scanned": len(asset_rows) if originals_scanned is None else originals_scanned,
        "duplicate_groups": len(all_groups),
        "unreviewed_groups": sum(not group["reviewed"] for group in all_groups),
        "redundant_copies": sum(group["copy_count"] - 1 for group in all_groups),
        "optimized_copies": sum(group["optimized_copies"] for group in all_groups),
        "reclaimable_bytes": sum(group["reclaimable_bytes"] for group in all_groups),
    }

    normalized_query = " ".join(query.lower().split())
    filtered = [
        group
        for group in all_groups
        if (
            not normalized_query
            or normalized_query in group["sha256"]
            or any(
                normalized_query in str(copy["source_name"]).lower()
                or normalized_query in str(copy["project_name"]).lower()
                for copy in group["copies"]
            )
        )
        and (review_state == "all" or group["reviewed"] == (review_state == "reviewed"))
    ]
    if sort == "most_copies":
        filtered.sort(key=lambda group: (-group["copy_count"], -group["reclaimable_bytes"], group["sha256"]))
    elif sort == "newest":
        filtered.sort(key=lambda group: (group["_newest"], group["sha256"]), reverse=True)
    else:
        filtered.sort(key=lambda group: (-group["reclaimable_bytes"], -group["copy_count"], group["sha256"]))
    for group in filtered:
        group.pop("_newest", None)
    return {"summary": summary, "groups": filtered[:limit]}


@router.get("/editor/models", response_model=list[EditorModelResponse])
def list_editor_models() -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            """
            SELECT slug, display_name, provider, available, refreshed_at
            FROM editor_models
            WHERE available = true
            ORDER BY sort_order, display_name, slug
            """
        ).fetchall()
    if rows:
        return list(rows)
    settings = get_settings()
    return [
        {
            "slug": settings.chatgpt_model,
            "display_name": settings.chatgpt_model,
            "provider": "chatgpt_plan",
            "available": True,
            "refreshed_at": datetime.now(timezone.utc),
        }
    ]


@router.get("/music-tracks", response_model=list[MusicTrackResponse])
def list_music_tracks() -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            """
            SELECT id, title, artist, duration_seconds, mood, energy, bpm,
                   beat_grid_seconds,
                   license_name, license_source_url, allowed_platforms,
                   attribution, created_at
            FROM music_tracks
            WHERE active = true AND commercial_use = true AND synthetic_media = false
            ORDER BY mood, energy, title
            """
        ).fetchall()
    return list(rows)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    project_id = payload.id or uuid4()
    try:
        with connection() as database:
            row = database.execute(
                """
                INSERT INTO projects (id, name, brief, privacy_mode, ai_copy_allowed)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    project_id,
                    payload.name,
                    payload.brief,
                    payload.privacy_mode.value,
                    payload.ai_copy_allowed,
                ),
            ).fetchone()
    except UniqueViolation:
        with connection() as database:
            row = database.execute("SELECT * FROM projects WHERE id = %s", (project_id,)).fetchone()
        if row is None or (
            row["name"] != payload.name
            or row["brief"] != payload.brief
            or row["privacy_mode"] != payload.privacy_mode.value
            or row["ai_copy_allowed"] != payload.ai_copy_allowed
        ):
            raise HTTPException(status_code=409, detail="project ID is already in use") from None
    assert row is not None
    return row


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(limit: int = Query(default=50, ge=1, le=100)) -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM projects ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return list(rows)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID) -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM projects WHERE id = %s",
            (project_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return row


@router.get("/projects/{project_id}/assets", response_model=list[AssetResponse])
def list_assets(project_id: UUID) -> list[dict[str, Any]]:
    with connection() as database:
        project_exists = database.execute(
            "SELECT 1 FROM projects WHERE id = %s",
            (project_id,),
        ).fetchone()
        if project_exists is None:
            raise HTTPException(status_code=404, detail="project not found")
        rows = database.execute(
            "SELECT * FROM assets WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        ).fetchall()
    return list(rows)


@router.get("/assets/library", response_model=list[LibraryAssetResponse])
def list_library_assets(
    query: str = Query(default="", max_length=160),
    media_kind: Literal["all", "video", "image", "audio"] = "all",
    project_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    normalized_query = " ".join(query.split())
    clauses = [
        "assets.status = 'ready'",
        "assets.library_status = 'active'",
        "assets.mime_type IS NOT NULL",
        "assets.byte_size IS NOT NULL",
        "assets.sha256 IS NOT NULL",
        "asset_ingests.status = 'ready'",
    ]
    parameters: list[Any] = []
    if normalized_query:
        clauses.append("(assets.source_name ILIKE %s OR projects.name ILIKE %s)")
        pattern = f"%{normalized_query}%"
        parameters.extend((pattern, pattern))
    if media_kind != "all":
        clauses.append("assets.mime_type LIKE %s")
        parameters.append(f"{media_kind}/%")
    if project_id is not None:
        clauses.append("assets.project_id = %s")
        parameters.append(project_id)
    parameters.append(limit)

    with connection() as database:
        rows = database.execute(
            f"""
            WITH active_hash_counts AS (
                SELECT active_assets.sha256, COUNT(*)::integer AS asset_count
                FROM assets AS active_assets
                JOIN asset_ingests AS active_ingests
                  ON active_ingests.asset_id = active_assets.id
                WHERE active_assets.status = 'ready'
                  AND active_assets.library_status = 'active'
                  AND active_assets.sha256 IS NOT NULL
                  AND active_ingests.status = 'ready'
                GROUP BY active_assets.sha256
            )
            SELECT assets.id, assets.project_id, projects.name AS project_name,
                   assets.source_name, assets.mime_type, assets.byte_size,
                   assets.sha256, assets.created_at,
                   NULLIF(
                       asset_ingests.manifest #>> '{{probe,format,duration_seconds}}',
                       ''
                   )::double precision AS duration_seconds,
                   COALESCE(
                       asset_ingests.manifest #>> '{{derived,thumbnail}}',
                       ''
                   ) <> '' AS thumbnail_available
            FROM assets
            JOIN projects ON projects.id = assets.project_id
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            LEFT JOIN active_hash_counts ON active_hash_counts.sha256 = assets.sha256
            LEFT JOIN asset_duplicate_reviews
              ON asset_duplicate_reviews.sha256 = assets.sha256
             AND asset_duplicate_reviews.asset_count = active_hash_counts.asset_count
            WHERE {' AND '.join(clauses)}
              AND (
                  asset_duplicate_reviews.canonical_asset_id IS NULL
                  OR asset_duplicate_reviews.canonical_asset_id = assets.id
              )
            ORDER BY assets.created_at DESC, assets.id DESC
            LIMIT %s
            """,
            parameters,
        ).fetchall()
    return list(rows)


@router.get("/catalog/status", response_model=CatalogStatusResponse)
def get_catalog_status() -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            """
            SELECT COUNT(*)::integer AS assets_total,
                   COUNT(*) FILTER (WHERE status = 'ready')::integer AS assets_ready,
                   COUNT(*) FILTER (WHERE status IN ('pending', 'running'))::integer AS assets_pending,
                   COUNT(*) FILTER (WHERE status = 'failed')::integer AS assets_failed,
                   COALESCE(SUM(segment_count), 0)::integer AS segments_total,
                   COALESCE(SUM(transcript_segment_count), 0)::integer AS transcript_segments,
                   COALESCE(SUM(scene_segment_count), 0)::integer AS scene_segments,
                   COALESCE(MAX(catalog_version), '1.0') AS catalog_version,
                   (SELECT COUNT(*)::integer FROM asset_story_indexes
                    WHERE status = 'ready') AS story_assets_ready,
                   (SELECT COALESCE(SUM(moment_count), 0)::integer
                    FROM asset_story_indexes WHERE status = 'ready') AS story_moments,
                   (SELECT COALESCE(MAX(story_version), '1.0')
                    FROM asset_story_indexes WHERE status = 'ready') AS story_version
            FROM asset_catalogs
            """
        ).fetchone()
    assert row is not None
    return row


@router.get("/catalog/search", response_model=CatalogSearchResponse)
def search_catalog(
    query: str = Query(min_length=1, max_length=160),
    media_kind: Literal["all", "video", "image", "audio"] = "all",
    project_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise HTTPException(status_code=422, detail="catalogue query cannot be blank")
    clauses = [
        "assets.status = 'ready'",
        "assets.library_status = 'active'",
        "asset_catalogs.status = 'ready'",
        "("
        "asset_catalog_segments.search_vector @@ search.value "
        "OR (asset_catalog_segments.segment_kind = 'asset' "
        "AND (assets.source_name ILIKE %s OR projects.name ILIKE %s))"
        ")",
    ]
    pattern = f"%{normalized_query}%"
    parameters: list[Any] = [
        normalized_query,
        pattern,
        pattern,
        pattern,
        pattern,
    ]
    if media_kind != "all":
        clauses.append("assets.mime_type LIKE %s")
        parameters.append(f"{media_kind}/%")
    if project_id is not None:
        clauses.append("assets.project_id = %s")
        parameters.append(project_id)
    parameters.append(limit)
    with connection() as database:
        text_rows = database.execute(
            f"""
            WITH search AS (
                SELECT websearch_to_tsquery('simple', %s) AS value
            )
            SELECT asset_catalog_segments.id AS segment_id,
                   assets.id AS asset_id, assets.project_id,
                   projects.name AS project_name, assets.source_name,
                   assets.mime_type, assets.byte_size, assets.sha256,
                   NULLIF(
                       asset_ingests.manifest #>> '{{probe,format,duration_seconds}}',
                       ''
                   )::double precision AS duration_seconds,
                   COALESCE(
                       asset_ingests.manifest #>> '{{derived,thumbnail}}',
                       ''
                   ) <> '' AS thumbnail_available,
                   asset_catalog_segments.segment_kind,
                   asset_catalog_segments.start_seconds,
                   asset_catalog_segments.end_seconds,
                   asset_catalog_segments.text,
                   asset_catalog_segments.facts,
                   asset_catalog_segments.source_model,
                   assets.created_at,
                   GREATEST(
                       ts_rank_cd(asset_catalog_segments.search_vector, search.value),
                       CASE
                           WHEN asset_catalog_segments.segment_kind = 'asset'
                                AND (assets.source_name ILIKE %s OR projects.name ILIKE %s)
                           THEN 0.05
                           ELSE 0
                       END
                   )::double precision AS rank
            FROM asset_catalog_segments
            CROSS JOIN search
            JOIN assets ON assets.id = asset_catalog_segments.asset_id
            JOIN projects ON projects.id = assets.project_id
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            JOIN asset_catalogs ON asset_catalogs.asset_id = assets.id
            LEFT JOIN asset_duplicate_reviews
              ON asset_duplicate_reviews.sha256 = assets.sha256
             AND asset_duplicate_reviews.asset_count = (
                 SELECT COUNT(*)
                 FROM assets AS matching_assets
                 JOIN asset_ingests AS matching_ingests
                   ON matching_ingests.asset_id = matching_assets.id
                 WHERE matching_assets.sha256 = assets.sha256
                   AND matching_assets.status = 'ready'
                   AND matching_assets.library_status = 'active'
                   AND matching_ingests.status = 'ready'
             )
            WHERE {' AND '.join(clauses)}
              AND (
                  asset_duplicate_reviews.canonical_asset_id IS NULL
                  OR asset_duplicate_reviews.canonical_asset_id = assets.id
              )
            ORDER BY rank DESC,
                     asset_catalog_segments.segment_kind = 'transcript' DESC,
                     assets.created_at DESC,
                     asset_catalog_segments.start_seconds
            LIMIT %s
            """,
            parameters,
        ).fetchall()
    text_results: list[dict[str, Any]] = []
    for source_row in text_rows:
        row = dict(source_row)
        row["evidence_kinds"] = [
            "spoken_words" if row["segment_kind"] == "transcript" else "metadata"
        ]
        row["visual_frame_id"] = None
        row["visual_frame_seconds"] = None
        text_results.append(row)

    visual_results: list[dict[str, Any]] = []
    if media_kind != "audio":
        try:
            query_embedding = embed_text(normalized_query)
            visual_clauses = [
                "assets.status = 'ready'",
                "assets.library_status = 'active'",
                "asset_visual_indexes.status = 'ready'",
                "asset_visual_indexes.canonical_asset_id = assets.id",
            ]
            visual_parameters: list[Any] = []
            if media_kind != "all":
                visual_clauses.append("assets.mime_type LIKE %s")
                visual_parameters.append(f"{media_kind}/%")
            if project_id is not None:
                visual_clauses.append("assets.project_id = %s")
                visual_parameters.append(project_id)
            with connection() as database:
                candidates = database.execute(
                    f"""
                    SELECT asset_visual_embeddings.id AS segment_id,
                           assets.id AS asset_id, assets.project_id,
                           projects.name AS project_name, assets.source_name,
                           assets.mime_type, assets.byte_size, assets.sha256,
                           NULLIF(
                               asset_ingests.manifest #>> '{{probe,format,duration_seconds}}',
                               ''
                           )::double precision AS duration_seconds,
                           true AS thumbnail_available,
                           asset_visual_embeddings.start_seconds,
                           asset_visual_embeddings.end_seconds,
                           asset_visual_embeddings.frame_seconds,
                           asset_visual_embeddings.embedding,
                           asset_visual_embeddings.source_model,
                           assets.created_at
                    FROM asset_visual_embeddings
                    JOIN assets ON assets.id = asset_visual_embeddings.asset_id
                    JOIN projects ON projects.id = assets.project_id
                    JOIN asset_ingests ON asset_ingests.asset_id = assets.id
                    JOIN asset_visual_indexes
                      ON asset_visual_indexes.asset_id = assets.id
                    WHERE {' AND '.join(visual_clauses)}
                    """,
                    visual_parameters,
                ).fetchall()
            best_by_asset: dict[Any, tuple[float, dict[str, Any]]] = {}
            for source_row in candidates:
                score = normalized_dot(query_embedding, source_row["embedding"])
                existing = best_by_asset.get(source_row["asset_id"])
                if existing is None or score > existing[0]:
                    best_by_asset[source_row["asset_id"]] = (score, dict(source_row))
            for score, source_row in select_visual_matches(list(best_by_asset.values()), limit):
                visual_results.append(
                    {
                        "segment_id": source_row["segment_id"],
                        "asset_id": source_row["asset_id"],
                        "project_id": source_row["project_id"],
                        "project_name": source_row["project_name"],
                        "source_name": source_row["source_name"],
                        "mime_type": source_row["mime_type"],
                        "byte_size": source_row["byte_size"],
                        "sha256": source_row["sha256"],
                        "duration_seconds": source_row["duration_seconds"],
                        "thumbnail_available": True,
                        "segment_kind": "visual",
                        "start_seconds": source_row["start_seconds"],
                        "end_seconds": source_row["end_seconds"],
                        "text": "",
                        "facts": {"evidence": "local visual embedding similarity"},
                        "source_model": source_row["source_model"],
                        "rank": max(0.0, score),
                        "evidence_kinds": ["visual"],
                        "visual_frame_id": source_row["segment_id"],
                        "visual_frame_seconds": source_row["frame_seconds"],
                        "created_at": source_row["created_at"],
                    }
                )
        except Exception as error:
            # Text search remains useful while the local encoder is starting or unavailable.
            print(f"visual catalogue search deferred: {error}", flush=True)
            visual_results = []

    combined: dict[Any, dict[str, Any]] = {}
    for row in text_results:
        combined.setdefault(row["asset_id"], row)
    for visual in sorted(visual_results, key=lambda row: row["rank"], reverse=True):
        existing = combined.get(visual["asset_id"])
        if existing is None:
            combined[visual["asset_id"]] = visual
            continue
        existing["evidence_kinds"] = list(dict.fromkeys([*existing["evidence_kinds"], "visual"]))
        existing["visual_frame_id"] = visual["visual_frame_id"]
        existing["visual_frame_seconds"] = visual["visual_frame_seconds"]
        existing["facts"] = {**existing["facts"], "visual_evidence": True}
        existing["rank"] = max(float(existing["rank"]), float(visual["rank"])) + 0.1

    results = sorted(
        combined.values(),
        key=lambda row: (
            -float(row["rank"]),
            row["segment_kind"] != "transcript",
            -row["created_at"].timestamp(),
        ),
    )[:limit]
    return {"query": normalized_query, "total": len(results), "results": results}


@router.get("/catalog/visual/status", response_model=VisualIndexStatusResponse)
def get_visual_index_status() -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            """
            SELECT COUNT(*)::integer AS assets_total,
                   COUNT(*) FILTER (WHERE status = 'ready')::integer AS assets_ready,
                   COUNT(*) FILTER (WHERE status = 'aliased')::integer AS assets_aliased,
                   COUNT(*) FILTER (WHERE status IN ('pending', 'running'))::integer AS assets_pending,
                   COUNT(*) FILTER (WHERE status = 'failed')::integer AS assets_failed,
                   COALESCE(SUM(frame_count), 0)::integer AS frames_total
            FROM asset_visual_indexes
            """
        ).fetchone()
    assert row is not None
    return {
        **row,
        "model_id": VISUAL_MODEL_ID,
        "model_revision": VISUAL_MODEL_REVISION,
        "index_version": VISUAL_INDEX_VERSION,
        "local_only": True,
    }


@router.post("/catalog/visual/reindex", response_model=VisualReindexResponse)
def reindex_visual_catalog(asset_id: UUID | None = None) -> dict[str, int]:
    clauses = ["canonical_asset_id = asset_id", "status <> 'aliased'"]
    parameters: list[Any] = []
    if asset_id is not None:
        clauses.append("asset_id = %s")
        parameters.append(asset_id)
    with connection() as database:
        result = database.execute(
            f"""
            UPDATE asset_visual_indexes
            SET status = 'pending', attempts = 0, lease_expires_at = NULL,
                error = NULL, completed_at = NULL, updated_at = now()
            WHERE {' AND '.join(clauses)}
            """,
            parameters,
        )
        queued_assets = result.rowcount
    return {"queued_assets": queued_assets}


@router.get("/catalog/visual/frames/{frame_id}")
def get_visual_index_frame(frame_id: int) -> FileResponse:
    with connection() as database:
        row = database.execute(
            """
            SELECT asset_visual_embeddings.frame_path
            FROM asset_visual_embeddings
            JOIN assets ON assets.id = asset_visual_embeddings.asset_id
            JOIN asset_visual_indexes ON asset_visual_indexes.asset_id = assets.id
            WHERE asset_visual_embeddings.id = %s
              AND assets.status = 'ready'
              AND assets.library_status = 'active'
              AND asset_visual_indexes.status = 'ready'
            """,
            (frame_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="visual index frame not found")
    path = resolve_source(get_settings().media_root, str(row["frame_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="visual index frame file is missing")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/assets/duplicates", response_model=DuplicateAuditResponse)
def list_exact_duplicates(
    query: str = Query(default="", max_length=160),
    review_state: Literal["all", "unreviewed", "reviewed"] = "all",
    sort: Literal["most_storage", "most_copies", "newest"] = "most_storage",
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    with connection() as database:
        originals_scanned = database.execute(
            """
            SELECT COUNT(*)::integer AS count
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.status = 'ready'
              AND assets.library_status = 'active'
              AND assets.sha256 IS NOT NULL
              AND assets.mime_type IS NOT NULL
              AND assets.byte_size IS NOT NULL
              AND asset_ingests.status = 'ready'
            """
        ).fetchone()
        asset_rows = database.execute(
            """
            WITH duplicate_hashes AS (
                SELECT assets.sha256
                FROM assets
                JOIN asset_ingests ON asset_ingests.asset_id = assets.id
                WHERE assets.status = 'ready'
                  AND assets.library_status = 'active'
                  AND assets.sha256 IS NOT NULL
                  AND assets.mime_type IS NOT NULL
                  AND assets.byte_size IS NOT NULL
                  AND asset_ingests.status = 'ready'
                GROUP BY assets.sha256
                HAVING COUNT(*) > 1
            )
            SELECT assets.id, assets.project_id, projects.name AS project_name,
                   assets.source_name, assets.mime_type, assets.byte_size,
                   assets.sha256, assets.created_at,
                   COUNT(DISTINCT job_assets.job_id)::integer AS job_references,
                   EXISTS (
                       SELECT 1
                       FROM asset_storage_optimizations
                       WHERE asset_storage_optimizations.asset_id = assets.id
                   ) AS storage_optimized,
                   COALESCE(
                       asset_ingests.manifest #>> '{derived,thumbnail}',
                       ''
                   ) <> '' AS thumbnail_available
            FROM assets
            JOIN duplicate_hashes ON duplicate_hashes.sha256 = assets.sha256
            JOIN projects ON projects.id = assets.project_id
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            LEFT JOIN job_assets ON job_assets.asset_id = assets.id
            WHERE assets.status = 'ready'
              AND assets.library_status = 'active'
              AND assets.sha256 IS NOT NULL
              AND assets.mime_type IS NOT NULL
              AND assets.byte_size IS NOT NULL
              AND asset_ingests.status = 'ready'
            GROUP BY assets.id, projects.name, asset_ingests.manifest
            ORDER BY assets.sha256, assets.created_at, assets.id
            """
        ).fetchall()
        review_rows = database.execute(
            """
            SELECT sha256, canonical_asset_id, asset_count, reviewed_at
            FROM asset_duplicate_reviews
            """
        ).fetchall()
    return _duplicate_audit(
        list(asset_rows),
        list(review_rows),
        originals_scanned=int(originals_scanned["count"]) if originals_scanned else 0,
        query=query,
        review_state=review_state,
        sort=sort,
        limit=limit,
    )


@router.post(
    "/assets/duplicates/{sha256}/review",
    response_model=DuplicateReviewResponse,
)
def review_exact_duplicate(
    sha256: str,
    payload: DuplicateReviewCreate,
) -> dict[str, Any]:
    if SHA256_PATTERN.fullmatch(sha256) is None:
        raise HTTPException(status_code=422, detail="invalid SHA-256")
    with connection() as database:
        candidates = database.execute(
            """
            SELECT assets.id
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.sha256 = %s
              AND assets.status = 'ready'
              AND assets.library_status = 'active'
              AND asset_ingests.status = 'ready'
            FOR UPDATE OF assets
            """,
            (sha256,),
        ).fetchall()
        candidate_ids = {row["id"] for row in candidates}
        if len(candidate_ids) < 2:
            raise HTTPException(status_code=404, detail="exact duplicate group not found")
        if payload.canonical_asset_id not in candidate_ids:
            raise HTTPException(
                status_code=422,
                detail="canonical asset must be an active member of this exact duplicate group",
            )
        row = database.execute(
            """
            INSERT INTO asset_duplicate_reviews (
                sha256, canonical_asset_id, asset_count, reviewed_at, updated_at
            )
            VALUES (%s, %s, %s, now(), now())
            ON CONFLICT (sha256) DO UPDATE SET
                canonical_asset_id = EXCLUDED.canonical_asset_id,
                asset_count = EXCLUDED.asset_count,
                reviewed_at = now(),
                updated_at = now()
            RETURNING sha256, canonical_asset_id, asset_count, reviewed_at
            """,
            (sha256, payload.canonical_asset_id, len(candidate_ids)),
        ).fetchone()
    assert row is not None
    return row


@router.post(
    "/assets/duplicates/{sha256}/cleanup",
    response_model=DuplicateCleanupResponse,
)
def cleanup_exact_duplicate(
    sha256: str,
    payload: DuplicateCleanupCreate,
) -> dict[str, Any]:
    """Share physical storage for one currently reviewed exact-duplicate group."""

    if SHA256_PATTERN.fullmatch(sha256) is None:
        raise HTTPException(status_code=422, detail="invalid SHA-256")

    settings = get_settings()
    with connection() as database:
        rows = database.execute(
            """
            SELECT assets.id, assets.storage_key, assets.byte_size,
                   assets.sha256, assets.status, assets.library_status,
                   asset_ingests.status AS ingest_status
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.sha256 = %s
              AND assets.status = 'ready'
              AND assets.library_status = 'active'
              AND asset_ingests.status = 'ready'
            ORDER BY assets.created_at, assets.id
            FOR UPDATE OF assets
            """,
            (sha256,),
        ).fetchall()
        if len(rows) < 2:
            raise HTTPException(status_code=404, detail="exact duplicate group not found")

        review = database.execute(
            """
            SELECT canonical_asset_id, asset_count
            FROM asset_duplicate_reviews
            WHERE sha256 = %s
            FOR UPDATE
            """,
            (sha256,),
        ).fetchone()
        if review is None or int(review["asset_count"]) != len(rows):
            raise HTTPException(
                status_code=409,
                detail="review this exact duplicate group again before cleanup",
            )
        if review["canonical_asset_id"] != payload.canonical_asset_id:
            raise HTTPException(
                status_code=409,
                detail="the cleanup selection no longer matches the reviewed canonical record",
            )

        by_id = {row["id"]: row for row in rows}
        canonical = by_id.get(payload.canonical_asset_id)
        if canonical is None:
            raise HTTPException(status_code=409, detail="reviewed canonical record is unavailable")
        canonical_path = resolve_source(settings.media_root, str(canonical["storage_key"]))

        # A newly selected canonical may previously have shared storage under a
        # different review. It is now the representative record, so only the
        # other records remain optimization aliases in the audit ledger.
        database.execute(
            "DELETE FROM asset_storage_optimizations WHERE asset_id = %s",
            (payload.canonical_asset_id,),
        )

        optimized_asset_ids: list[UUID] = []
        bytes_reclaimed = 0
        already_optimized = 0
        for row in rows:
            if row["id"] == payload.canonical_asset_id:
                continue
            duplicate_path = resolve_source(settings.media_root, str(row["storage_key"]))
            try:
                result = share_exact_duplicate_storage(
                    canonical_path,
                    duplicate_path,
                    expected_sha256=sha256,
                    expected_size=int(row["byte_size"]),
                )
            except (OSError, ValueError) as error:
                raise HTTPException(
                    status_code=409,
                    detail=f"cleanup stopped safely: {error}",
                ) from error
            optimized_asset_ids.append(row["id"])
            bytes_reclaimed += result.bytes_reclaimed
            already_optimized += int(result.already_shared)
            database.execute(
                """
                INSERT INTO asset_storage_optimizations (
                    asset_id, canonical_asset_id, sha256, bytes_reclaimed,
                    source_storage_key, canonical_storage_key,
                    device, inode, reason, optimized_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'reviewed_cleanup', now())
                ON CONFLICT (asset_id) DO UPDATE SET
                    canonical_asset_id = EXCLUDED.canonical_asset_id,
                    sha256 = EXCLUDED.sha256,
                    bytes_reclaimed = asset_storage_optimizations.bytes_reclaimed
                        + EXCLUDED.bytes_reclaimed,
                    source_storage_key = EXCLUDED.source_storage_key,
                    canonical_storage_key = EXCLUDED.canonical_storage_key,
                    device = EXCLUDED.device,
                    inode = EXCLUDED.inode,
                    reason = EXCLUDED.reason,
                    optimized_at = now()
                """,
                (
                    row["id"],
                    payload.canonical_asset_id,
                    sha256,
                    result.bytes_reclaimed,
                    row["storage_key"],
                    canonical["storage_key"],
                    result.device,
                    result.inode,
                ),
            )

        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            SELECT DISTINCT job_assets.job_id, 'duplicate_storage_optimized', %s
            FROM job_assets
            WHERE job_assets.asset_id = ANY(%s::uuid[])
            """,
            (
                Jsonb(
                    {
                        "sha256": sha256,
                        "canonical_asset_id": str(payload.canonical_asset_id),
                        "optimized_asset_ids": [str(asset_id) for asset_id in optimized_asset_ids],
                        "bytes_reclaimed": bytes_reclaimed,
                        "method": "hardlink",
                    }
                ),
                optimized_asset_ids,
            ),
        )

    return {
        "sha256": sha256,
        "canonical_asset_id": payload.canonical_asset_id,
        "optimized_asset_ids": optimized_asset_ids,
        "optimized_copies": len(optimized_asset_ids),
        "bytes_reclaimed": bytes_reclaimed,
        "already_optimized": already_optimized,
    }


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    project_id: UUID,
    payload: JobCreate,
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    job_id = payload.id or uuid4()
    try:
        with connection() as database:
            if payload.editor_model is not None:
                available_model = database.execute(
                    "SELECT 1 FROM editor_models WHERE slug = %s AND available = true",
                    (payload.editor_model,),
                ).fetchone()
                catalog_exists = database.execute("SELECT 1 FROM editor_models LIMIT 1").fetchone()
                if available_model is None and not (
                    catalog_exists is None and payload.editor_model == get_settings().chatgpt_model
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="the selected editor model is not available to the connected ChatGPT account",
                    )
            row = database.execute(
                """
                INSERT INTO jobs (
                    id, project_id, recipe, target_duration_seconds,
                    edit_style, music_mode, target_platform, must_include,
                    audience, story_goal, desired_feeling, ending_instruction,
                    editor_model, reasoning_effort, output_aspect, creative_profile_id,
                    brand_kit_id, publishing_preset, created_by_login
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    job_id,
                    project_id,
                    payload.recipe.value,
                    payload.target_duration_seconds,
                    payload.edit_style.value,
                    payload.music_mode.value,
                    payload.target_platform.value,
                    payload.must_include,
                    payload.audience,
                    payload.story_goal,
                    payload.desired_feeling,
                    payload.ending_instruction,
                    payload.editor_model,
                    payload.reasoning_effort.value,
                    payload.output_aspect.value,
                    payload.creative_profile_id,
                    payload.brand_kit_id,
                    payload.publishing_preset.value,
                    actor_login(x_gm_user_login),
                ),
            ).fetchone()
    except ForeignKeyViolation as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    except UniqueViolation:
        with connection() as database:
            row = database.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if row is None or (
            row["project_id"] != project_id
            or row["recipe"] != payload.recipe.value
            or row["target_duration_seconds"] != payload.target_duration_seconds
            or row["edit_style"] != payload.edit_style.value
            or row["music_mode"] != payload.music_mode.value
            or row["target_platform"] != payload.target_platform.value
            or row["must_include"] != payload.must_include
            or row["audience"] != payload.audience
            or row["story_goal"] != payload.story_goal
            or row["desired_feeling"] != payload.desired_feeling
            or row["ending_instruction"] != payload.ending_instruction
            or row["editor_model"] != payload.editor_model
            or row["reasoning_effort"] != payload.reasoning_effort.value
            or row["output_aspect"] != payload.output_aspect.value
            or row["creative_profile_id"] != payload.creative_profile_id
            or row["brand_kit_id"] != payload.brand_kit_id
            or row["publishing_preset"] != payload.publishing_preset.value
        ):
            raise HTTPException(status_code=409, detail="job ID is already in use") from None
    assert row is not None
    return row


@router.post("/jobs/{job_id}/assets", response_model=JobAssetAttachResponse)
def attach_job_assets(job_id: UUID, payload: JobAssetAttach) -> dict[str, Any]:
    with connection() as database:
        job = database.execute(
            "SELECT id, status FROM jobs WHERE id = %s FOR UPDATE",
            (job_id,),
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] != "draft":
            raise HTTPException(
                status_code=409,
                detail="source media can only be attached before editing starts",
            )

        rows = database.execute(
            """
            SELECT assets.id, assets.status, assets.library_status,
                   asset_ingests.status AS analysis_status
            FROM assets
            LEFT JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.id = ANY(%s::uuid[])
            """,
            (payload.asset_ids,),
        ).fetchall()
        found = {row["id"]: row for row in rows}
        missing = [asset_id for asset_id in payload.asset_ids if asset_id not in found]
        if missing:
            raise HTTPException(status_code=404, detail="one or more library assets were not found")
        unavailable = [
            asset_id
            for asset_id in payload.asset_ids
            if found[asset_id]["status"] != "ready"
            or found[asset_id]["analysis_status"] != "ready"
            or found[asset_id]["library_status"] != "active"
        ]
        if unavailable:
            raise HTTPException(
                status_code=409,
                detail="one or more library assets are not ready for editing",
            )

        attached_count = 0
        for asset_id in payload.asset_ids:
            inserted = database.execute(
                """
                INSERT INTO job_assets (job_id, asset_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING asset_id
                """,
                (job_id, asset_id),
            ).fetchone()
            attached_count += int(inserted is not None)
        if attached_count:
            database.execute(
                """
                INSERT INTO job_events (job_id, event_type, payload)
                VALUES (%s, 'server_assets_attached', %s)
                """,
                (
                    job_id,
                    Jsonb({
                        "asset_ids": [str(asset_id) for asset_id in payload.asset_ids],
                        "attached_count": attached_count,
                    }),
                ),
            )
    return {
        "job_id": job_id,
        "asset_ids": payload.asset_ids,
        "attached_count": attached_count,
    }


@router.get("/jobs/{job_id}/assets", response_model=list[AssetResponse])
def list_job_assets(job_id: UUID) -> list[dict[str, Any]]:
    with connection() as database:
        job = database.execute("SELECT 1 FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        rows = database.execute(
            """
            SELECT assets.*
            FROM job_assets
            JOIN assets ON assets.id = job_assets.asset_id
            WHERE job_assets.job_id = %s
            ORDER BY job_assets.created_at, assets.created_at, assets.id
            """,
            (job_id,),
        ).fetchall()
    return list(rows)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID) -> dict[str, Any]:
    with connection() as database:
        row = database.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row


@router.get("/projects/{project_id}/jobs", response_model=list[JobResponse])
def list_jobs(project_id: UUID) -> list[dict[str, Any]]:
    with connection() as database:
        project_exists = database.execute(
            "SELECT 1 FROM projects WHERE id = %s",
            (project_id,),
        ).fetchone()
        if project_exists is None:
            raise HTTPException(status_code=404, detail="project not found")
        rows = database.execute(
            "SELECT * FROM jobs WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return list(rows)


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: UUID) -> dict[str, Any]:
    with connection() as database:
        row = database.execute("SELECT * FROM assets WHERE id = %s", (asset_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return row


@router.get("/assets/{asset_id}/analysis", response_model=AssetAnalysisResponse)
def get_asset_analysis(asset_id: UUID) -> dict[str, Any]:
    with connection() as database:
        asset_exists = database.execute(
            "SELECT 1 FROM assets WHERE id = %s", (asset_id,)
        ).fetchone()
        if asset_exists is None:
            raise HTTPException(status_code=404, detail="asset not found")
        row = database.execute(
            "SELECT * FROM asset_ingests WHERE asset_id = %s", (asset_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="asset analysis has not been queued")
    return row


@router.get("/assets/{asset_id}/thumbnail")
def get_asset_thumbnail(asset_id: UUID) -> FileResponse:
    with connection() as database:
        row = database.execute(
            """
            SELECT assets.source_name,
                   asset_ingests.manifest #>> '{derived,thumbnail}' AS thumbnail_path
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.id = %s
              AND assets.status = 'ready'
              AND asset_ingests.status = 'ready'
            """,
            (asset_id,),
        ).fetchone()
    if row is None or not row["thumbnail_path"]:
        raise HTTPException(status_code=404, detail="asset thumbnail not found")
    path = resolve_source(get_settings().media_root, str(row["thumbnail_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset thumbnail file is missing")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.post(
    "/projects/{project_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_asset(project_id: UUID, payload: AssetCreate) -> dict[str, Any]:
    settings = get_settings()
    if payload.byte_size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file exceeds the configured upload limit")

    asset_id = payload.id or uuid4()
    storage_key = f"{project_id}/{asset_id}"
    try:
        with connection() as database:
            if payload.job_id is not None:
                job = database.execute(
                    "SELECT project_id FROM jobs WHERE id = %s",
                    (payload.job_id,),
                ).fetchone()
                if job is None:
                    raise HTTPException(status_code=404, detail="job not found")
                if job["project_id"] != project_id:
                    raise HTTPException(status_code=409, detail="job belongs to a different project")
            row = database.execute(
                """
                INSERT INTO assets (
                    id, project_id, source_name, storage_key, mime_type, byte_size
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    asset_id,
                    project_id,
                    payload.source_name,
                    storage_key,
                    payload.mime_type,
                    payload.byte_size,
                ),
            ).fetchone()
            if payload.job_id is not None:
                database.execute(
                    "INSERT INTO job_assets (job_id, asset_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (payload.job_id, asset_id),
                )
    except ForeignKeyViolation as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    except UniqueViolation:
        with connection() as database:
            row = database.execute("SELECT * FROM assets WHERE id = %s", (asset_id,)).fetchone()
        if row is None or (
            row["project_id"] != project_id
            or row["source_name"] != payload.source_name
            or row["mime_type"] != payload.mime_type
            or row["byte_size"] != payload.byte_size
        ):
            raise HTTPException(status_code=409, detail="asset ID is already in use") from None
        if payload.job_id is not None:
            with connection() as database:
                job = database.execute(
                    "SELECT project_id FROM jobs WHERE id = %s", (payload.job_id,)
                ).fetchone()
                if job is None:
                    raise HTTPException(status_code=404, detail="job not found")
                if job["project_id"] != project_id:
                    raise HTTPException(status_code=409, detail="job belongs to a different project")
                database.execute(
                    "INSERT INTO job_assets (job_id, asset_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (payload.job_id, asset_id),
                )
    assert row is not None
    return row
