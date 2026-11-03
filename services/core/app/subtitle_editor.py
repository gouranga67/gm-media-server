"""Explicit draft/apply workflow for the selected saved reel's subtitles."""

from copy import deepcopy
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.database import connection
from app.media_analysis import resolve_source
from app.productization import assert_job_capacity
from app.subtitle_document import SubtitleEdit, fingerprint, make_document, parse_ass, validate_cues

router = APIRouter(prefix="/api/v1", tags=["subtitles"])


def load_run(database, job_id, run_id):
    row = database.execute(
        """SELECT r.*, p.document AS plan_document, p.speech_precision_snapshot,
                  p.subtitle_document
           FROM edit_runs r JOIN edit_plans p ON p.id=r.edit_plan_id
           WHERE r.id=%s AND r.job_id=%s""", (run_id, job_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "saved edit version not found")
    if row["status"] != "ready":
        raise HTTPException(409, "wait for this preview to finish before editing subtitles")
    return row


def base_document(row):
    if row.get("subtitle_document"):
        from app.subtitle_document import corrected_document, retime_document
        return retime_document(corrected_document(row["subtitle_document"], row.get("caption_corrections") or []), row["plan_document"])
    manifest = row.get("manifest") or {}
    events = manifest.get("subtitle_events")
    if not isinstance(events, list):
        key = (manifest.get("outputs") or {}).get("captions")
        if key and str(key).endswith(".ass"):
            try:
                events = parse_ass(resolve_source(get_settings().media_root, key).read_text())
            except (OSError, ValueError):
                events = None
    if events is None:
        # Old previews may have expired. Reconstruct from their saved timing,
        # never from new alignment, and do not render or load a model here.
        from app.editor_context import build_editor_context
        from app.speech_precision import apply_snapshot
        from app.edit_plan import MontageEditPlan, TalkingHeadEditPlan
        from app.edit_renderer import caption_events, adjust_caption_timing
        from app.montage_renderer import montage_caption_events
        from app.finishing_tools import finish_caption_events
        context = build_editor_context(row["job_id"], include_internal_paths=True)
        apply_snapshot(context, row.get("speech_precision_snapshot") or {}, get_settings())
        model = MontageEditPlan if row["plan_document"]["recipe"] == "montage" else TalkingHeadEditPlan
        plan = model.model_validate(row["plan_document"])
        extract = montage_caption_events if isinstance(plan, MontageEditPlan) else caption_events
        events = finish_caption_events(adjust_caption_timing(
            extract(plan, context["assets"], row.get("caption_corrections") or []),
            float(plan.caption_timing_offset_seconds)), plan.finishing)
    result = make_document(row["plan_document"], events)
    result["caption_corrections_snapshot"] = row.get("caption_corrections") or []
    return result


def load_draft(database, run_id):
    return database.execute("SELECT * FROM subtitle_drafts WHERE edit_run_id=%s", (run_id,)).fetchone()


def response(row, base, draft):
    valid = draft and draft["document"].get("base_hash") == fingerprint(base)
    return {"run_id": row["id"], "version": row["version"], "base_hash": fingerprint(base),
            "revision": draft["revision"] if draft else 0,
            "cues": draft["document"]["cues"] if valid else base["cues"], "baseline": base["cues"],
            "position": row["plan_document"].get("caption_position", "lower_safe"),
            "saved": bool(valid), "applied_run_id": draft.get("applied_run_id") if valid else None,
            "duration": base["duration"], "hosted_model_calls": 0,
            "notice": "The video shows saved subtitles. Apply your draft to update the video."}


@router.get("/jobs/{job_id}/edits/{run_id}/subtitles")
def get_subtitles(job_id: UUID, run_id: UUID):
    with connection() as database:
        row = load_run(database, job_id, run_id)
        return response(row, base_document(row), load_draft(database, run_id))


@router.put("/jobs/{job_id}/edits/{run_id}/subtitles")
def save_subtitles(job_id: UUID, run_id: UUID, payload: SubtitleEdit):
    with connection() as database:
        database.execute("SELECT id FROM jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        row = load_run(database, job_id, run_id)
        base, draft = base_document(row), load_draft(database, run_id)
        if payload.base_hash != fingerprint(base) or payload.revision != (draft["revision"] if draft else 0):
            raise HTTPException(409, "These subtitles changed in another tab. Reload before saving your draft.")
        try:
            cues = validate_cues([c.model_dump() for c in payload.cues], base["duration"])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        saved = database.execute(
            """INSERT INTO subtitle_drafts(edit_run_id, document) VALUES(%s,%s)
               ON CONFLICT(edit_run_id) DO UPDATE SET document=excluded.document,
                   revision=subtitle_drafts.revision+1, applied_run_id=NULL, updated_at=now()
               RETURNING *""", (run_id, Jsonb({**base, "base_hash": payload.base_hash, "cues": cues})),
        ).fetchone()
        return response(row, base, saved)


class SubtitleApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(gt=0)


@router.post("/jobs/{job_id}/edits/{run_id}/subtitles/apply", status_code=202)
def apply_subtitles(job_id: UUID, run_id: UUID, payload: SubtitleApply):
    with connection() as database:
        database.execute("SELECT id FROM jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        row = load_run(database, job_id, run_id)
        base, draft = base_document(row), load_draft(database, run_id)
        if (not draft or draft["revision"] != payload.revision or payload.base_hash != fingerprint(base)
                or draft["document"].get("base_hash") != payload.base_hash):
            raise HTTPException(409, "Save the current subtitle draft before applying it.")
        if draft.get("applied_run_id"):
            return database.execute("SELECT * FROM edit_runs WHERE id=%s", (draft["applied_run_id"],)).fetchone()
        if draft["document"]["cues"] == base["cues"]:
            raise HTTPException(422, "There are no subtitle changes to apply.")
        latest = database.execute("SELECT id, version, status FROM edit_runs WHERE job_id=%s ORDER BY version DESC LIMIT 1", (job_id,)).fetchone()
        if latest["id"] != row["id"]:
            raise HTTPException(409, "A newer edit exists. Open its subtitles before applying changes.")
        assert_job_capacity(database, job_id)
        document = deepcopy(draft["document"])
        document.pop("base_hash", None)
        document["cues"] = validate_cues(document["cues"], base["duration"])
        plan = database.execute(
            """INSERT INTO edit_plans(job_id,version,schema_version,document,provider,model,document_sha256,
                                      speech_precision_snapshot,subtitle_document)
               SELECT job_id,%s,schema_version,document,'local_subtitles','timed_captions_v1',document_sha256,
                      speech_precision_snapshot,%s FROM edit_plans WHERE id=%s RETURNING id""",
            (latest["version"] + 1, Jsonb(document), row["edit_plan_id"]),
        ).fetchone()
        created = database.execute(
            """INSERT INTO edit_runs(job_id,version,edit_plan_id,based_on_run_id,provider,model,
                       caption_corrections,caption_settings,locked_elements,duration_policy)
               VALUES(%s,%s,%s,%s,'local_subtitles','timed_captions_v1',%s,%s,%s,%s) RETURNING *""",
            (job_id, latest["version"] + 1, plan["id"], run_id, Jsonb(row.get("caption_corrections") or []),
             Jsonb(row.get("caption_settings") or {}), Jsonb(row.get("locked_elements") or []),
             Jsonb(row["duration_policy"]) if row.get("duration_policy") else None),
        ).fetchone()
        database.execute("UPDATE subtitle_drafts SET applied_run_id=%s WHERE edit_run_id=%s", (created["id"], run_id))
        database.execute("UPDATE jobs SET status='previewing', updated_at=now() WHERE id=%s", (job_id,))
        database.execute("INSERT INTO job_events(job_id,event_type,payload) VALUES(%s,'subtitles_applied',%s)",
                         (job_id, Jsonb({"version": created["version"], "based_on_version": row["version"], "hosted_model_calls": 0})))
        return created
