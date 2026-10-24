from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from psycopg.errors import UniqueViolation

from app.config import get_settings
from app.database import connection
from app.media_analysis import resolve_source
from app.schemas import (
    LibraryAssetDetailResponse,
    LibraryAssetStateResponse,
    LibraryAssetUpdate,
    LibraryCollectionCreate,
    LibraryCollectionResponse,
    ManagedLibraryAssetResponse,
)


router = APIRouter(prefix="/api/v1/library", tags=["library"])


MANAGED_ASSET_SELECT = """
    SELECT assets.id, assets.project_id, projects.name AS project_name,
           assets.source_name,
           COALESCE(asset_library_metadata.display_name, assets.source_name) AS display_name,
           COALESCE(asset_library_metadata.notes, '') AS notes,
           COALESCE(asset_library_metadata.favorite, false) AS favorite,
           COALESCE(asset_library_metadata.tags, ARRAY[]::text[]) AS tags,
           assets.library_status, assets.mime_type, assets.byte_size,
           assets.sha256, assets.created_at,
           COALESCE(asset_library_metadata.updated_at, assets.updated_at) AS updated_at,
           NULLIF(
               asset_ingests.manifest #>> '{probe,format,duration_seconds}',
               ''
           )::double precision AS duration_seconds,
           COALESCE(asset_ingests.manifest #>> '{derived,thumbnail}', '') <> ''
               AS thumbnail_available,
           COUNT(DISTINCT job_assets.job_id)::integer AS job_references,
           COUNT(DISTINCT library_collection_assets.collection_id)::integer
               AS collection_count,
           asset_visual_indexes.status AS visual_status
    FROM assets
    JOIN projects ON projects.id = assets.project_id
    JOIN asset_ingests ON asset_ingests.asset_id = assets.id
    LEFT JOIN asset_library_metadata ON asset_library_metadata.asset_id = assets.id
    LEFT JOIN job_assets ON job_assets.asset_id = assets.id
    LEFT JOIN library_collection_assets ON library_collection_assets.asset_id = assets.id
    LEFT JOIN asset_visual_indexes ON asset_visual_indexes.asset_id = assets.id
"""


def _managed_asset(database: Any, asset_id: UUID) -> dict[str, Any] | None:
    return database.execute(
        f"""
        {MANAGED_ASSET_SELECT}
        WHERE assets.id = %s
          AND assets.status = 'ready'
          AND asset_ingests.status = 'ready'
        GROUP BY assets.id, projects.name, asset_ingests.manifest,
                 asset_library_metadata.asset_id, asset_visual_indexes.status
        """,
        (asset_id,),
    ).fetchone()


@router.get("/assets", response_model=list[ManagedLibraryAssetResponse])
def list_managed_assets(
    query: str = Query(default="", max_length=160),
    state: Literal["active", "archived", "all"] = "active",
    media_kind: Literal["all", "video", "image", "audio"] = "all",
    favorite: bool | None = None,
    tag: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=250, ge=1, le=500),
) -> list[dict[str, Any]]:
    clauses = ["assets.status = 'ready'", "asset_ingests.status = 'ready'"]
    parameters: list[Any] = []
    if state != "all":
        clauses.append("assets.library_status = %s")
        parameters.append(state)
    if media_kind != "all":
        clauses.append("assets.mime_type LIKE %s")
        parameters.append(f"{media_kind}/%")
    if favorite is not None:
        clauses.append("COALESCE(asset_library_metadata.favorite, false) = %s")
        parameters.append(favorite)
    if tag:
        normalized_tag = " ".join(tag.split()).lower()
        clauses.append("%s = ANY(COALESCE(asset_library_metadata.tags, ARRAY[]::text[]))")
        parameters.append(normalized_tag)
    normalized_query = " ".join(query.split())
    if normalized_query:
        pattern = f"%{normalized_query}%"
        clauses.append(
            "(assets.source_name ILIKE %s OR projects.name ILIKE %s "
            "OR asset_library_metadata.display_name ILIKE %s "
            "OR asset_library_metadata.notes ILIKE %s "
            "OR array_to_string(asset_library_metadata.tags, ' ') ILIKE %s)"
        )
        parameters.extend([pattern] * 5)
    parameters.append(limit)

    with connection() as database:
        rows = database.execute(
            f"""
            {MANAGED_ASSET_SELECT}
            WHERE {' AND '.join(clauses)}
            GROUP BY assets.id, projects.name, asset_ingests.manifest,
                     asset_library_metadata.asset_id, asset_visual_indexes.status
            ORDER BY COALESCE(asset_library_metadata.favorite, false) DESC,
                     COALESCE(asset_library_metadata.updated_at, assets.created_at) DESC,
                     assets.id DESC
            LIMIT %s
            """,
            parameters,
        ).fetchall()
    return list(rows)


@router.get("/assets/{asset_id}", response_model=LibraryAssetDetailResponse)
def get_library_asset_detail(asset_id: UUID) -> dict[str, Any]:
    with connection() as database:
        asset = _managed_asset(database, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="library asset not found")
        evidence = database.execute(
            """
            SELECT id, segment_kind, start_seconds, end_seconds, text, source_model
            FROM asset_catalog_segments
            WHERE asset_id = %s AND segment_kind IN ('transcript', 'scene', 'image')
            ORDER BY start_seconds, segment_kind, segment_index
            LIMIT 500
            """,
            (asset_id,),
        ).fetchall()
        visual_frames = database.execute(
            """
            SELECT id, start_seconds, end_seconds, frame_seconds
            FROM asset_visual_embeddings
            WHERE asset_id = %s
            ORDER BY frame_seconds
            LIMIT 240
            """,
            (asset_id,),
        ).fetchall()
        collections = database.execute(
            """
            SELECT library_collections.id, library_collections.name,
                   library_collections.description,
                   COUNT(all_assets.asset_id)::integer AS asset_count,
                   library_collections.created_at, library_collections.updated_at
            FROM library_collections
            JOIN library_collection_assets selected
              ON selected.collection_id = library_collections.id
             AND selected.asset_id = %s
            LEFT JOIN library_collection_assets all_assets
              ON all_assets.collection_id = library_collections.id
            GROUP BY library_collections.id
            ORDER BY library_collections.name
            """,
            (asset_id,),
        ).fetchall()
    return {
        "asset": asset,
        "evidence": list(evidence),
        "visual_frames": list(visual_frames),
        "collections": list(collections),
    }


@router.patch("/assets/{asset_id}", response_model=ManagedLibraryAssetResponse)
def update_library_asset(asset_id: UUID, payload: LibraryAssetUpdate) -> dict[str, Any]:
    with connection() as database:
        exists = database.execute(
            "SELECT 1 FROM assets WHERE id = %s AND status = 'ready'",
            (asset_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="library asset not found")
        database.execute(
            """
            INSERT INTO asset_library_metadata (
                asset_id, display_name, notes, favorite, tags
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (asset_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                notes = EXCLUDED.notes,
                favorite = EXCLUDED.favorite,
                tags = EXCLUDED.tags,
                updated_at = now()
            """,
            (
                asset_id,
                payload.display_name,
                payload.notes,
                payload.favorite,
                payload.tags,
            ),
        )
        row = _managed_asset(database, asset_id)
    assert row is not None
    return row


def _set_library_state(asset_id: UUID, next_state: Literal["active", "archived"]) -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            """
            UPDATE assets
            SET library_status = %s, updated_at = now()
            WHERE id = %s AND status = 'ready'
            RETURNING id
            """,
            (next_state, asset_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="library asset not found")
    return {"asset_id": asset_id, "library_status": next_state}


@router.post("/assets/{asset_id}/archive", response_model=LibraryAssetStateResponse)
def archive_library_asset(asset_id: UUID) -> dict[str, Any]:
    return _set_library_state(asset_id, "archived")


@router.post("/assets/{asset_id}/restore", response_model=LibraryAssetStateResponse)
def restore_library_asset(asset_id: UUID) -> dict[str, Any]:
    return _set_library_state(asset_id, "active")


@router.get("/assets/{asset_id}/preview")
def preview_library_asset(asset_id: UUID) -> FileResponse:
    with connection() as database:
        row = database.execute(
            """
            SELECT assets.mime_type, assets.storage_key,
                   asset_ingests.manifest #>> '{derived,proxy}' AS proxy_path
            FROM assets
            JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE assets.id = %s
              AND assets.status = 'ready'
              AND asset_ingests.status = 'ready'
            """,
            (asset_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="library asset not found")
    path_key = row["proxy_path"] or row["storage_key"]
    path = resolve_source(get_settings().media_root, str(path_key))
    media_type = str(row["mime_type"])
    if row["proxy_path"] and media_type.startswith("video/"):
        media_type = "video/mp4"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/collections", response_model=list[LibraryCollectionResponse])
def list_collections() -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            """
            SELECT library_collections.id, library_collections.name,
                   library_collections.description,
                   COUNT(library_collection_assets.asset_id)::integer AS asset_count,
                   library_collections.created_at, library_collections.updated_at
            FROM library_collections
            LEFT JOIN library_collection_assets
              ON library_collection_assets.collection_id = library_collections.id
            GROUP BY library_collections.id
            ORDER BY lower(library_collections.name)
            """
        ).fetchall()
    return list(rows)


@router.post(
    "/collections",
    response_model=LibraryCollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_collection(payload: LibraryCollectionCreate) -> dict[str, Any]:
    try:
        with connection() as database:
            row = database.execute(
                """
                INSERT INTO library_collections (name, description)
                VALUES (%s, %s)
                RETURNING id, name, description, 0::integer AS asset_count,
                          created_at, updated_at
                """,
                (payload.name, payload.description),
            ).fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a collection with that name already exists") from error
    assert row is not None
    return row


@router.put("/collections/{collection_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_collection_asset(collection_id: UUID, asset_id: UUID) -> Response:
    try:
        with connection() as database:
            result = database.execute(
                """
                INSERT INTO library_collection_assets (collection_id, asset_id)
                SELECT library_collections.id, assets.id
                FROM assets
                JOIN library_collections ON library_collections.id = %s
                WHERE assets.id = %s AND assets.status = 'ready'
                ON CONFLICT DO NOTHING
                """,
                (collection_id, asset_id),
            )
            if result.rowcount == 0:
                collection = database.execute(
                    "SELECT 1 FROM library_collections WHERE id = %s",
                    (collection_id,),
                ).fetchone()
                asset = database.execute(
                    "SELECT 1 FROM assets WHERE id = %s AND status = 'ready'",
                    (asset_id,),
                ).fetchone()
                if collection is None or asset is None:
                    raise HTTPException(status_code=404, detail="collection or asset not found")
    except UniqueViolation as error:
        raise HTTPException(status_code=404, detail="collection not found") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/collections/{collection_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_asset(collection_id: UUID, asset_id: UUID) -> Response:
    with connection() as database:
        database.execute(
            "DELETE FROM library_collection_assets WHERE collection_id = %s AND asset_id = %s",
            (collection_id, asset_id),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: UUID) -> Response:
    with connection() as database:
        result = database.execute("DELETE FROM library_collections WHERE id = %s", (collection_id,))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="collection not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

