"""Resolve a compatible existing engine once, without an extra model call."""

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from uuid import UUID
from psycopg.types.json import Jsonb
from app.brief_direction import read_brief
from app.database import connection

router = APIRouter(prefix="/api/v1/jobs", tags=["assembly"])


def decide_assembly(
    job: dict[str, Any], assets: list[dict[str, Any]]
) -> dict[str, Any]:
    direction = read_brief(job)
    if job.get("_selected_recorded_concept"):
        # A generated concept brief also contains quoted source dialogue. Those
        # words are evidence, not new instructions about purpose or pacing.
        direction = {
            **direction,
            "purpose": job["reel_intent"]
            if job.get("reel_intent") in {"story", "promotion", "bloopers"}
            else "story",
            "explicit_purpose": False,
            "preserve_speech": True,
            "visual_led": False,
            "style": None,
        }
    mode = job.get("assembly_mode") or job.get("recipe") or "talking_head"
    purpose = str(job.get("reel_intent") or "auto")
    if (
        purpose != "auto"
        and direction["explicit_purpose"]
        and purpose != direction["purpose"]
    ):
        raise ValueError(
            "The explicit purpose conflicts with the brief. Choose Follow my brief or update the brief before starting."
        )
    purpose = direction["purpose"] if purpose == "auto" else purpose
    speech = [
        a
        for a in assets
        if a.get("has_video")
        and a.get("has_audio")
        and a.get("library_role") != "broll"
        and any(
            str(s.get("text") or "").strip() for s in a.get("transcript_segments", [])
        )
    ]
    pictures = [
        a
        for a in assets
        if a.get("has_video") or str(a.get("mime_type") or "").startswith("image/")
    ]
    if not pictures:
        raise ValueError(
            "Add a video or photo. Audio-only sources cannot form the picture track in the current editor."
        )
    separate_voice = [
        a
        for a in assets
        if a.get("has_audio")
        and not a.get("has_video")
        and a.get("transcript_segments")
    ]
    if separate_voice:
        raise ValueError(
            "Independent audio-file narration is not supported by these engines. Remove that source or use its speech in a video recording."
        )
    if not speech and (
        direction["preserve_speech"] or purpose == "bloopers" or mode == "talking_head"
    ):
        raise ValueError(
            "No usable recorded video speech was found for this request. Add talking footage, or remove the speech/blooper direction and make a visual edit."
        )
    if mode != "auto":
        recipe = mode
        reason = "Using your explicit assembly override."
    elif speech and (
        direction["preserve_speech"]
        or purpose == "bloopers"
        or not direction["visual_led"]
    ):
        recipe = "talking_head"
        reason = "Keep recorded speech continuous; use relevant supporting pictures as cutaways."
    else:
        recipe = "montage"
        reason = "Assemble the selected pictures and scenes as a visual sequence."
    if recipe == "talking_head" and not speech:
        raise ValueError(
            "No usable recorded video speech was found for a speech-led edit. Choose Automatic or Montage, or add talking footage."
        )
    if recipe == "montage" and len(pictures) == 1 and not pictures[0].get("has_video"):
        raise ValueError(
            "The current montage engine needs more than a single still image. Add another photo or video; it will not duplicate the image to fill time."
        )
    if (
        recipe == "montage"
        and len(pictures) == 1
        and float(pictures[0].get("duration_seconds") or 0) < 1
    ):
        raise ValueError(
            "Add another visual source or a longer video; montage needs two distinct ranges of at least half a second."
        )
    style = str(job.get("edit_style") or "energetic")
    if job.get("pacing_mode") == "auto" and direction["style"]:
        style = direction["style"]
    if (
        job.get("pacing_mode") == "manual"
        and direction["style"]
        and style != direction["style"]
    ):
        requested = (
            "gentle"
            if direction["style"] == "calm"
            else direction["style"].replace("_", " ")
        )
        raise ValueError(
            f"The brief asks for {requested} pacing but the explicit style is {style.replace('_', ' ')}. "
            "Choose Follow my brief for pacing or change that setting."
        )
    warnings = []
    return {
        "version": 1,
        "mode": mode,
        "recipe": recipe,
        "edit_style": style,
        "purpose": purpose,
        "reason": reason,
        "warnings": warnings,
        "requested_edit_style": job.get("edit_style") or "energetic",
        "brief_first": True,
        "label": "Speech with supporting pictures"
        if recipe == "talking_head"
        else "Visual sequence",
        "hosted_model_calls": 0,
    }


def _context_job(
    context: dict[str, Any], row: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        **(context["job"] if row is None else row),
        "brief": context["project"]["brief"],
        "_selected_recorded_concept": bool(context.get("selected_concept")),
    }


def preview_assembly(context: dict[str, Any]) -> dict[str, Any]:
    job = context["job"]
    saved = job.get("assembly_decision")
    if saved:
        return {
            "ready": bool(context.get("ready_for_editing")),
            "locked": True,
            "decision": saved,
            "error": None
            if context.get("ready_for_editing")
            else "Waiting for source analysis.",
        }
    if not context.get("ready_for_editing"):
        return {
            "ready": False,
            "locked": False,
            "decision": None,
            "error": "Waiting for source analysis.",
        }
    try:
        decision = decide_assembly(_context_job(context), context["assets"])
        return {"ready": True, "locked": False, "decision": decision, "error": None}
    except ValueError as error:
        return {"ready": False, "locked": False, "decision": None, "error": str(error)}


def persist_assembly(database: Any, context: dict[str, Any]) -> dict[str, Any]:
    row = database.execute(
        "SELECT * FROM jobs WHERE id=%s FOR UPDATE", (UUID(context["job"]["id"]),)
    ).fetchone()
    if row is None:
        raise LookupError("job not found")
    if row.get("assembly_decision"):
        return row["assembly_decision"]
    if not context.get("ready_for_editing"):
        raise ValueError("Wait for source analysis before choosing an assembly.")
    decision = decide_assembly(_context_job(context, row), context["assets"])
    database.execute(
        """UPDATE jobs SET recipe=%s,edit_style=%s,assembly_decision=%s,updated_at=now() WHERE id=%s""",
        (decision["recipe"], decision["edit_style"], Jsonb(decision), row["id"]),
    )
    database.execute(
        "INSERT INTO job_events(job_id,event_type,payload) VALUES(%s,'assembly_resolved',%s)",
        (row["id"], Jsonb(decision)),
    )
    return decision


@router.get("/{job_id}/assembly")
def inspect_assembly(job_id: UUID):
    from app.editor_context import build_editor_context

    try:
        context = build_editor_context(job_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="job not found") from error
    result = preview_assembly(context)
    result["settings"] = {
        key: context["job"].get(key)
        for key in ("assembly_mode", "pacing_mode", "edit_style", "reel_intent")
    }
    return result


class AssemblySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assembly_mode: Literal["auto", "talking_head", "montage"]
    pacing_mode: Literal["auto", "manual"]
    edit_style: Literal["clean", "energetic", "high_impact", "calm"]
    reel_intent: Literal["auto", "story", "promotion", "bloopers"]


@router.put("/{job_id}/assembly")
def update_assembly(job_id: UUID, payload: AssemblySettings):
    with connection() as database:
        row = database.execute(
            "SELECT id FROM jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        if database.execute(
            "SELECT 1 FROM edit_runs WHERE job_id=%s LIMIT 1", (job_id,)
        ).fetchone():
            raise HTTPException(
                status_code=409,
                detail="Assembly is frozen after planning starts. Existing previews and revisions keep their engine.",
            )
        database.execute(
            """UPDATE jobs SET assembly_mode=%s,pacing_mode=%s,edit_style=%s,reel_intent=%s,
            assembly_decision=NULL,updated_at=now() WHERE id=%s""",
            (
                payload.assembly_mode,
                payload.pacing_mode,
                payload.edit_style,
                payload.reel_intent,
                job_id,
            ),
        )
    return inspect_assembly(job_id)
