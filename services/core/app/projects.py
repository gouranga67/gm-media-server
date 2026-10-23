from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.config import get_settings
from app.database import connection
from app.schemas import (
    AssetAnalysisResponse,
    AssetCreate,
    AssetResponse,
    JobCreate,
    JobResponse,
    ProjectCreate,
    ProjectResponse,
)


router = APIRouter(prefix="/api/v1", tags=["projects"])


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


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(project_id: UUID, payload: JobCreate) -> dict[str, Any]:
    job_id = payload.id or uuid4()
    try:
        with connection() as database:
            row = database.execute(
                """
                INSERT INTO jobs (id, project_id, recipe)
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (job_id, project_id, payload.recipe.value),
            ).fetchone()
    except ForeignKeyViolation as error:
        raise HTTPException(status_code=404, detail="project not found") from error
    except UniqueViolation:
        with connection() as database:
            row = database.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if row is None or row["project_id"] != project_id or row["recipe"] != payload.recipe.value:
            raise HTTPException(status_code=409, detail="job ID is already in use") from None
    assert row is not None
    return row


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
