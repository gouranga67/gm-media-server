"""Durable standalone imports and bounded library browsing; no model calls."""
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database import connection

router = APIRouter()


class IntakeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["review", "dismiss"] = "review"

    @field_validator("asset_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("select each import once")
        return value


INTAKE_SELECT = """
    SELECT assets.id, assets.source_name, assets.mime_type, assets.byte_size,
           assets.created_at, assets.project_id, projects.name AS project_name,
           COALESCE(meta.display_name, assets.source_name) AS display_name,
           COALESCE(meta.media_role, 'auto') AS media_role,
           COALESCE(meta.media_category, 'auto') AS media_category,
           COALESCE(ingest.manifest #>> '{derived,thumbnail}', '') <> '' AS thumbnail_available,
           CASE WHEN assets.status IN ('quarantined', 'failed') OR ingest.status = 'failed' OR catalog.status = 'failed'
                THEN 'failed'
                WHEN assets.status = 'ready' AND ingest.status = 'ready' AND catalog.status = 'ready'
                THEN 'ready'
                WHEN assets.status = 'uploading' THEN 'uploading' ELSE 'processing' END AS intake_status,
           left(COALESCE(drive_import.error, ingest.error, catalog.error, ''), 1000) AS error
    FROM library_intakes intake JOIN assets ON assets.id = intake.asset_id
    JOIN projects ON projects.id = assets.project_id
    LEFT JOIN asset_library_metadata meta ON meta.asset_id = assets.id
    LEFT JOIN asset_ingests ingest ON ingest.asset_id = assets.id
    LEFT JOIN asset_catalogs catalog ON catalog.asset_id = assets.id
    LEFT JOIN google_drive_imports drive_import ON drive_import.asset_id = assets.id
"""
INTAKE_BASE = INTAKE_SELECT + " WHERE intake.reviewed_at IS NULL AND assets.library_status = 'active'"


@router.get("/intake/status")
def intake_status(asset_ids: list[UUID] = Query(min_length=1, max_length=100)) -> list[dict[str, Any]]:
    with connection() as database:
        return list(database.execute("SELECT id, intake_status, error FROM (" + INTAKE_SELECT
            + " WHERE intake.asset_id = ANY(%s)) selected", (asset_ids,)).fetchall())


@router.get("/intake")
def list_intake(query: str = Query(default="", max_length=160),
                limit: int = Query(default=60, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    pattern = f"%{query.strip()}%"
    with connection() as database:
        row = database.execute(
            "WITH imports AS (" + INTAKE_BASE + """), matching AS (
                SELECT * FROM imports WHERE display_name ILIKE %s OR source_name ILIKE %s OR project_name ILIKE %s
            ), page AS (SELECT * FROM matching ORDER BY created_at DESC, id LIMIT %s OFFSET %s)
            SELECT (SELECT count(*)::integer FROM matching) AS total,
                   (SELECT count(*)::integer FROM imports) AS inbox_count,
                   COALESCE((SELECT jsonb_agg(to_jsonb(page) || jsonb_build_object('folders',
                       (SELECT COALESCE(jsonb_agg(jsonb_build_object('id', folder.id, 'name', folder.name)
                           ORDER BY lower(folder.name), folder.id), '[]'::jsonb)
                        FROM library_collection_assets member JOIN library_collections folder ON folder.id = member.collection_id
                        WHERE member.asset_id = page.id)) ORDER BY page.created_at DESC, page.id)
                       FROM page), '[]'::jsonb) AS items
            """, (pattern, pattern, pattern, limit, offset),
        ).fetchone()
    return {**row, "offset": offset, "limit": limit}


@router.post("/intake/review")
def review_intake(payload: IntakeReview) -> dict[str, Any]:
    with connection() as database:
        rows = database.execute(
            """SELECT intake.asset_id, assets.status, ingest.status AS ingest_status, catalog.status AS catalog_status
               FROM library_intakes intake JOIN assets ON assets.id = intake.asset_id
               LEFT JOIN asset_ingests ingest ON ingest.asset_id = intake.asset_id
               LEFT JOIN asset_catalogs catalog ON catalog.asset_id = intake.asset_id
               WHERE intake.asset_id = ANY(%s) ORDER BY intake.asset_id FOR UPDATE OF intake""",
            (payload.asset_ids,),
        ).fetchall()
        if len(rows) != len(payload.asset_ids):
            raise HTTPException(status_code=409, detail="some imports are no longer available; refresh the Inbox")
        if payload.action == "review" and any(row["status"] != "ready" or row["ingest_status"] != "ready"
                or row["catalog_status"] != "ready" for row in rows):
            raise HTTPException(status_code=409, detail="wait for analysis to finish before marking these imports reviewed")
        database.execute(
            "UPDATE library_intakes SET reviewed_at = COALESCE(reviewed_at, now()) WHERE asset_id = ANY(%s)",
            (payload.asset_ids,),
        )
    return {"updated": len(rows), "action": payload.action}


def browse_filter(view, category, favorite, collection_id, unfiled, query, match_ids,
                  media_kind="all", project_id=None, for_editing=False):
    clauses = ["assets.status = 'ready'", "ingest.status = 'ready'", "assets.library_status = %s"]
    values: list[Any] = ["archived" if view == "trash" else "active"]
    if for_editing:
        clauses += ["assets.library_status = 'active'", "assets.sha256 IS NOT NULL",
                    "assets.byte_size IS NOT NULL", "assets.mime_type IS NOT NULL"]
    if media_kind != "all":
        clauses.append("assets.mime_type LIKE %s")
        values.append(media_kind + "/%")
    if project_id:
        clauses.append("assets.project_id = %s")
        values.append(project_id)
    if view in ("image", "audio"):
        clauses.append("assets.mime_type LIKE %s")
        values.append(view + "/%")
    elif view in ("talking", "broll", "unsorted"):
        clauses += ["assets.mime_type LIKE 'video/%%'", "COALESCE(meta.media_role, 'auto') = %s"]
        values.append("auto" if view == "unsorted" else view)
    if category != "all":
        clauses.append("COALESCE(meta.media_category, 'auto') = %s")
        values.append(category)
    if favorite:
        clauses.append("COALESCE(meta.favorite, false)")
    if collection_id:
        clauses.append("EXISTS (SELECT 1 FROM library_collection_assets member WHERE member.asset_id = assets.id AND member.collection_id = %s)")
        values.append(collection_id)
    if unfiled:
        clauses.append("NOT EXISTS (SELECT 1 FROM library_collection_assets member WHERE member.asset_id = assets.id)")
    if query.strip():
        clauses.append("""(concat_ws(' ', assets.source_name, projects.name, meta.display_name, meta.notes,
            array_to_string(meta.tags, ' ')) ILIKE %s OR assets.id = ANY(%s))""")
        values += [f"%{query.strip()}%", match_ids]
    return " AND ".join(clauses), values


@router.get("/browse")
def browse_library(
    view: Literal["all", "talking", "broll", "image", "audio", "unsorted", "trash"] = "all",
    category: Literal["all", "auto", "review", "product", "scene", "document", "other"] = "all",
    favorite: bool = False, collection_id: UUID | None = None, unfiled: bool = False,
    query: str = Query(default="", max_length=160),
    match_ids: list[UUID] = Query(default=[], max_length=100),
    copies: bool = False, sort: Literal["newest", "name", "largest"] = "newest",
    limit: int = Query(default=60, ge=1, le=100), offset: int = Query(default=0, ge=0),
    media_kind: Literal["all", "video", "image", "audio"] = "all",
    project_id: UUID | None = None, for_editing: bool = False,
) -> dict[str, Any]:
    # The search service supplies at most 100 speech/visual hits. Text search still
    # covers the whole library. Filtering and canonical fallback happen BEFORE paging.
    from app.library import MANAGED_ASSET_SELECT
    where, values = browse_filter(view, category, favorite, collection_id, unfiled, query, match_ids,
                                  media_kind, project_id, for_editing)
    order = {"newest": "created_at DESC, id", "name": "lower(display_name), id", "largest": "byte_size DESC, id"}[sort]
    if query.strip() and sort == "newest":
        order = "search_order, " + order
    with connection() as database:
        result = database.execute(
            """WITH candidates AS (
                SELECT assets.id, assets.created_at, assets.byte_size,
                       COALESCE(meta.display_name, assets.source_name) AS display_name,
                       review.canonical_asset_id,
                       COALESCE(array_position(%s::uuid[], assets.id), 2147483647) AS search_order
                FROM assets JOIN projects ON projects.id = assets.project_id
                JOIN asset_ingests ingest ON ingest.asset_id = assets.id
                LEFT JOIN asset_library_metadata meta ON meta.asset_id = assets.id
                LEFT JOIN asset_duplicate_reviews review ON review.sha256 = assets.sha256
                WHERE """ + where + """
            ), filtered AS (
                SELECT * FROM candidates c WHERE %s OR c.canonical_asset_id IS NULL OR c.canonical_asset_id = c.id
                    OR NOT EXISTS (SELECT 1 FROM candidates keeper WHERE keeper.id = c.canonical_asset_id)
            ), page AS (SELECT * FROM filtered ORDER BY """ + order + """ LIMIT %s OFFSET %s)
            SELECT (SELECT count(*)::integer FROM filtered) AS total,
                COALESCE((SELECT array_agg(id ORDER BY """ + order + """) FROM page), ARRAY[]::uuid[]) AS ids""",
            [match_ids, *values, copies or view == "trash", limit, offset],
        ).fetchone()
        rows = database.execute(MANAGED_ASSET_SELECT + """
            WHERE assets.id = ANY(%s)
            GROUP BY assets.id, projects.name, asset_ingests.manifest, asset_library_metadata.asset_id,
                     asset_visual_indexes.status, asset_duplicate_reviews.canonical_asset_id
            """, (result["ids"],)).fetchall() if result["ids"] else []
        by_id = {row["id"]: row for row in rows}
        stats = database.execute("""SELECT count(*) FILTER (WHERE library_status = 'active')::integer AS active,
            count(*) FILTER (WHERE library_status = 'archived')::integer AS trash,
            COALESCE(sum(byte_size), 0)::bigint AS stored_bytes FROM assets WHERE status = 'ready'""").fetchone()
    return {"items": [by_id[id] for id in result["ids"] if id in by_id], "total": result["total"],
            "offset": offset, "limit": limit, "summary": stats}


PICKER_READY = """assets.status='ready' AND assets.library_status='active' AND ingest.status='ready'
    AND assets.sha256 IS NOT NULL AND assets.byte_size IS NOT NULL AND assets.mime_type IS NOT NULL"""


@router.get("/picker/projects")
def picker_projects() -> list[dict[str, Any]]:
    with connection() as database:
        return list(database.execute("""SELECT DISTINCT projects.id,projects.name FROM projects
            JOIN assets ON assets.project_id=projects.id JOIN asset_ingests ingest ON ingest.asset_id=assets.id
            WHERE """ + PICKER_READY + " ORDER BY projects.name,projects.id").fetchall())


@router.get("/selection")
def selected_library_assets(asset_ids: list[UUID] = Query(min_length=1, max_length=100)) -> list[dict[str, Any]]:
    # Exact selections are not replaced by a canonical duplicate or clipped to a recent page.
    with connection() as database:
        return list(database.execute("""SELECT assets.id,assets.project_id,projects.name AS project_name,
            assets.source_name,COALESCE(meta.display_name,assets.source_name) AS display_name,
            COALESCE(meta.media_role,'auto') AS media_role,assets.mime_type,assets.byte_size,assets.sha256,assets.created_at,
            NULLIF(ingest.manifest #>> '{probe,format,duration_seconds}','')::double precision AS duration_seconds,
            COALESCE(ingest.manifest #>> '{derived,thumbnail}','') <> '' AS thumbnail_available
            FROM assets JOIN projects ON projects.id=assets.project_id JOIN asset_ingests ingest ON ingest.asset_id=assets.id
            LEFT JOIN asset_library_metadata meta ON meta.asset_id=assets.id
            WHERE """ + PICKER_READY + " AND assets.id=ANY(%s::uuid[]) ORDER BY assets.id", (asset_ids,)).fetchall())
