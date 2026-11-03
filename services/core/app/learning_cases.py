"""Reusable owner-defined playback tasks. Saving a case never runs a model."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database import connection
from app.edit_plan import document_sha256
from app.learning_evidence import known_hashes, preview_available
from app.config import get_settings
from app.productization import actor_login, require_owner

router = APIRouter(prefix="/api/v1/learning/lab", tags=["evaluated learning"])

CASES_SQL = """SELECT c.id,c.job_id,c.baseline_run_id,c.label,c.recording_group,c.category,c.expectations,c.max_candidate_tokens,
    c.snapshot_hash,c.archived_at,c.created_at,c.snapshot->'sources' AS sources,
    left(c.snapshot#>>'{task,brief}',500) AS brief,
    r.version,r.status,r.preview_path,j.recipe,j.edit_style,j.reel_intent,j.story_goal,j.must_include,
    j.ending_instruction,j.archived_at AS job_archived_at,p.name,p.privacy_mode,
    EXISTS(SELECT 1 FROM edit_runs active WHERE active.job_id=j.id AND active.status IN ('pending','planning','rendering')) AS busy
    FROM learning_cases c JOIN edit_runs r ON r.id=c.baseline_run_id JOIN jobs j ON j.id=c.job_id
    JOIN projects p ON p.id=j.project_id ORDER BY c.created_at DESC,c.id LIMIT 100"""


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    job_id: UUID
    base_version: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=120)
    recording_group: str = Field(min_length=1, max_length=120)
    category: Literal["story", "speech", "captions", "visuals", "audio", "effects"] = "story"
    expectations: str = Field(min_length=1, max_length=1200)
    max_candidate_tokens: int | None = Field(default=None, ge=1, le=2_000_000)

    @field_validator("label", "expectations", "recording_group")
    @classmethod
    def clean_text(cls, value):
        value = " ".join(value.split())
        if not value or "\x00" in value:
            raise ValueError("describe the test and what a successful edit should preserve")
        return value


# The current revision is a delivery counter, not an editor setting. A finished
# trial advances it, and must remain scoreable against the saved ordinary cut.
TASK_SQL = """SELECT to_jsonb(j) - ARRAY['status','revision','updated_at','created_at','archived_at'] AS settings,
    p.brief,p.privacy_mode,p.ai_copy_allowed FROM jobs j JOIN projects p ON p.id=j.project_id
    WHERE j.id=%s AND j.archived_at IS NULL"""
SOURCES_SQL = """SELECT a.id,a.sha256,a.status AS asset_status,i.status AS analysis_status,md5(i.manifest::text) AS analysis_hash,
    COALESCE(m.display_name,a.source_name) AS display_name,COALESCE(m.media_role,'auto') AS media_role,
    COALESCE(m.media_category,'auto') AS media_category,COALESCE(m.notes,'') AS notes,COALESCE(m.tags,ARRAY[]::text[]) AS tags,
    (SELECT COALESCE(jsonb_agg(jsonb_build_array(r.start_seconds,r.end_seconds,r.role,r.note)
        ORDER BY r.start_seconds,r.id), '[]'::jsonb) FROM asset_range_annotations r WHERE r.asset_id=a.id) AS ranges
    FROM job_assets ja JOIN assets a ON a.id=ja.asset_id JOIN asset_ingests i ON i.asset_id=a.id
    LEFT JOIN asset_library_metadata m ON m.asset_id=a.id WHERE ja.job_id=%s
    ORDER BY ja.created_at,a.created_at,a.id"""


def task_snapshot(database, job_id, baseline):
    task = database.execute(TASK_SQL, (job_id,)).fetchone()
    sources = list(database.execute(SOURCES_SQL, (job_id,)).fetchall())
    # Detect missing ingests too; a join must not silently omit attached footage.
    count = database.execute("SELECT count(*) AS count FROM job_assets WHERE job_id=%s", (job_id,)).fetchone()["count"]
    if (not task or len(sources) != count or len(sources) > 100 or not known_hashes([source["sha256"] for source in sources])
            or any(source["asset_status"] != "ready" or source["analysis_status"] != "ready" for source in sources)):
        raise HTTPException(409, "the active task and every attached original need complete source analysis and checksums")
    plan = database.execute("SELECT document FROM edit_plans WHERE id=%s", (baseline["edit_plan_id"],)).fetchone()
    if not plan:
        raise HTTPException(409, "the baseline edit plan is unavailable")
    manifest = baseline.get("manifest") or {}
    if manifest.get("edit_plan_sha256") != document_sha256(plan["document"]):
        raise HTTPException(409, "re-render the baseline before saving a test case; rendered plan provenance is incomplete")
    rendered = [source.get("sha256") for source in manifest.get("sources", [])]
    if not known_hashes(rendered) or not set(rendered) <= {source["sha256"] for source in sources}:
        raise HTTPException(409, "the baseline's rendered source provenance is incomplete or changed")
    return jsonable_encoder({"version": 1, "job_id": str(job_id), "baseline_run_id": str(baseline["id"]),
        "baseline_plan_hash": document_sha256(plan["document"]), "task": task, "sources": sources})


def assert_case(database, case_id, job_id, baseline, *, new_trial=False):
    case = database.execute("SELECT * FROM learning_cases WHERE id=%s FOR SHARE", (case_id,)).fetchone()
    if not case or str(case["job_id"]) != str(job_id) or str(case["baseline_run_id"]) != str(baseline["id"]):
        raise HTTPException(409, "choose the saved test case for this exact baseline")
    if new_trial and case["archived_at"]:
        raise HTTPException(409, "restore this test case before starting another lesson trial")
    current = task_snapshot(database, job_id, baseline)
    if document_sha256(current) != case["snapshot_hash"]:
        raise HTTPException(409, "the brief, settings, source labels, ranges or analysis changed since this test was saved; use a fresh baseline")
    return case


@router.post("/cases")
def create_case(payload: CaseCreate, x_gm_user_login: str | None = Header(default=None)):
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    with connection() as database:
        # Same job lock/order as revision creation keeps registration and trial
        # creation from racing. This does not lock the whole media library.
        if not database.execute("SELECT id FROM jobs WHERE id=%s FOR UPDATE", (payload.job_id,)).fetchone():
            raise HTTPException(404, "job not found")
        existing = database.execute("SELECT c.*,r.version AS base_version FROM learning_cases c JOIN edit_runs r ON r.id=c.baseline_run_id "
            "WHERE c.id=%s OR (r.job_id=%s AND r.version=%s)", (payload.id,payload.job_id,payload.base_version)).fetchone()
        if existing:
            if (str(existing["id"]) != str(payload.id) or str(existing["job_id"]) != str(payload.job_id) or existing["base_version"] != payload.base_version
                    or any(existing[key] != getattr(payload,key) for key in ("label","recording_group","category","expectations","max_candidate_tokens"))):
                raise HTTPException(409, "this request or baseline already has a saved test case; open it instead")
            return {"id": existing["id"], "hosted_model_calls": 0}
        baseline = database.execute("SELECT * FROM edit_runs WHERE job_id=%s AND version=%s AND status='ready'",
            (payload.job_id,payload.base_version)).fetchone()
        if not baseline or baseline.get("evaluation_lesson_id") or not preview_available(baseline,get_settings().media_root):
            raise HTTPException(409, "save a playable ordinary edit as the baseline")
        snapshot = task_snapshot(database,payload.job_id,baseline)
        inserted = database.execute("""INSERT INTO learning_cases(id,job_id,baseline_run_id,label,recording_group,category,expectations,
            max_candidate_tokens,snapshot,snapshot_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING RETURNING id""",
            (payload.id,payload.job_id,baseline["id"],payload.label,payload.recording_group,payload.category,payload.expectations,
             payload.max_candidate_tokens,Jsonb(snapshot),document_sha256(snapshot),actor)).fetchone()
        if not inserted:
            raise HTTPException(409, "this baseline or request was saved concurrently; refresh the test cases")
    return {"id": payload.id, "hosted_model_calls": 0}


class CaseAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["archive", "restore"]


@router.post("/cases/{case_id}/status")
def case_status(case_id: UUID, payload: CaseAction, x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        row = database.execute("UPDATE learning_cases SET archived_at=" + ("now()" if payload.action == "archive" else "NULL")
            + " WHERE id=%s RETURNING id", (case_id,)).fetchone()
        if not row:
            raise HTTPException(404, "test case not found")
    return {"id": case_id, "status": payload.action, "hosted_model_calls": 0}
