from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from app.database import connection
from app.duration_policy import duration_preflight, duration_settings
from app.editor_context import build_editor_context

router = APIRouter(prefix="/api/v1/jobs", tags=["duration"])


class DurationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_mode: Literal["follow_story", "aim", "strict"]
    target_duration_seconds: Literal[15, 20, 30, 45, 60] = 45
    max_duration_seconds: int = Field(default=90, ge=5, le=120)


@router.get("/{job_id}/duration")
def inspect_duration(job_id: UUID):
    try:
        context = build_editor_context(job_id)
    except LookupError:
        raise HTTPException(404, "job not found") from None
    return {
        "settings": duration_settings(context["job"]),
        "assessment": duration_preflight(context),
    }


@router.put("/{job_id}/duration")
def update_duration(job_id: UUID, payload: DurationSettings):
    with connection() as database:
        if not database.execute(
            "SELECT id FROM jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone():
            raise HTTPException(404, "job not found")
        if database.execute(
            "SELECT 1 FROM edit_runs WHERE job_id=%s AND status IN ('pending','planning','rendering') LIMIT 1",
            (job_id,),
        ).fetchone():
            raise HTTPException(
                409,
                "Wait for the current edit attempt to finish before changing duration.",
            )
        database.execute(
            "UPDATE jobs SET duration_mode=%s,target_duration_seconds=%s,max_duration_seconds=%s,updated_at=now() WHERE id=%s",
            (
                payload.duration_mode,
                payload.target_duration_seconds,
                payload.max_duration_seconds,
                job_id,
            ),
        )
        # Only a failed latest attempt adopts changed limits. Completed versions
        # keep their frozen policy for exact re-renders, restore and export.
        database.execute(
            """UPDATE edit_runs SET duration_policy=%s WHERE job_id=%s AND status='failed'
            AND id=(SELECT id FROM edit_runs WHERE job_id=%s ORDER BY version DESC LIMIT 1)""",
            (Jsonb(payload.model_dump()), job_id, job_id),
        )
        database.execute(
            "INSERT INTO job_events(job_id,event_type,payload) VALUES(%s,'duration_settings_updated',%s)",
            (job_id, Jsonb(payload.model_dump())),
        )
    return inspect_duration(job_id)
