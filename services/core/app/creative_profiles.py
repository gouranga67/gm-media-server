from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from psycopg.errors import UniqueViolation

from app.database import connection
from app.schemas import (
    CreativeProfileCreate,
    CreativeProfileFromJobCreate,
    CreativeProfileResponse,
    CreativeProfileUpdate,
)


router = APIRouter(prefix="/api/v1", tags=["creative-profiles"])


@router.get("/creative-profiles", response_model=list[CreativeProfileResponse])
def list_creative_profiles() -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM creative_profiles ORDER BY updated_at DESC, lower(name)"
        ).fetchall()
    return list(rows)


def _insert_profile(database: Any, values: dict[str, Any]) -> dict[str, Any]:
    row = database.execute(
        """
        INSERT INTO creative_profiles (
            name, description, recipe, target_duration_seconds, edit_style,
            music_mode, target_platform, output_aspect, reasoning_effort, source_job_id,
            brand_kit_id, publishing_preset
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            values["name"],
            values["description"],
            values["recipe"],
            values["target_duration_seconds"],
            values["edit_style"],
            values["music_mode"],
            values["target_platform"],
            values["output_aspect"],
            values["reasoning_effort"],
            values.get("source_job_id"),
            values.get("brand_kit_id"),
            values.get("publishing_preset", "custom"),
        ),
    ).fetchone()
    assert row is not None
    return row


@router.post(
    "/creative-profiles",
    response_model=CreativeProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_creative_profile(payload: CreativeProfileCreate) -> dict[str, Any]:
    values = payload.model_dump(mode="json")
    try:
        with connection() as database:
            return _insert_profile(database, values)
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a creative profile with that name already exists") from error


@router.post(
    "/jobs/{job_id}/creative-profile",
    response_model=CreativeProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_creative_profile_from_job(
    job_id: UUID,
    payload: CreativeProfileFromJobCreate,
) -> dict[str, Any]:
    try:
        with connection() as database:
            job = database.execute(
                """
                SELECT id, recipe, target_duration_seconds, edit_style, music_mode,
                       target_platform, output_aspect, reasoning_effort,
                       brand_kit_id, publishing_preset
                FROM jobs WHERE id = %s
                """,
                (job_id,),
            ).fetchone()
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            delivered = database.execute(
                """
                SELECT 1 FROM final_exports
                WHERE job_id = %s AND status = 'ready'
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if delivered is None:
                raise HTTPException(status_code=409, detail="finish a final delivery before saving its creative profile")
            return _insert_profile(
                database,
                {
                    **job,
                    "name": payload.name,
                    "description": payload.description,
                    "source_job_id": job_id,
                },
            )
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a creative profile with that name already exists") from error


@router.put("/creative-profiles/{profile_id}", response_model=CreativeProfileResponse)
def update_creative_profile(profile_id: UUID, payload: CreativeProfileUpdate) -> dict[str, Any]:
    try:
        with connection() as database:
            row = database.execute(
                "UPDATE creative_profiles SET name=%s, description=%s, updated_at=now() WHERE id=%s RETURNING *",
                (payload.name, payload.description, profile_id),
            ).fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a creative profile with that name already exists") from error
    if row is None:
        raise HTTPException(status_code=404, detail="creative profile not found")
    return row


@router.delete("/creative-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creative_profile(profile_id: UUID) -> Response:
    with connection() as database:
        deleted = database.execute(
            "DELETE FROM creative_profiles WHERE id = %s",
            (profile_id,),
        )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="creative profile not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
