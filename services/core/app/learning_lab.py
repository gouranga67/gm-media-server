"""Explicit, source-separated lesson evaluation. No automatic paid experimentation."""

from __future__ import annotations
import re
from collections import defaultdict
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field
from app.database import connection
from app.productization import actor_login, require_owner
from app.take_quality import editing_policy
from app.config import get_settings
from app.edit_plan import document_sha256
from app.learning_evidence import comparison_evidence, evaluation_result, known_hashes, preview_available, usage_for_runs, with_trial_readiness, usage_snapshot

router = APIRouter(prefix="/api/v1/learning/lab", tags=["evaluated learning"])
NOTE_RULES = {
    "clean_pauses": (
        r"\b(dead (?:space|air)|long pause|bloopers?|false starts?|noise)\b",
        "Prefer clean complete speech takes, remove empty waiting and readiness chatter, and keep a comic pause only when the user requests that beat.",
    ),
    "product_referents": (
        r"\b(wrong product|another vid|audio didn.t match|different product|broll.*talking)\b",
        "Keep product names, claims and demonstrations attached to their actual source referent. Use relevant silent picture cutaways rather than mismatched speaking mouths.",
    ),
    "purposeful_variety": (
        r"\b(more (?:fx|effects|zoom)|not (?:enough|much).*fx|could have more)\b",
        "When effects are enabled, add restrained source-backed visual or sound emphasis at meaningful beats. Preserve story clarity and avoid decorating every sentence.",
    ),
    "safe_captions": (
        r"\b(subs?.*(?:wrong spot|position)|captions?.*(?:cover|position|safe)|subtitle.*position)\b",
        "Keep short synchronized captions within the chosen publishing safe area, clear of important product text and faces where the supplied framing permits.",
    ),
}


def propose_from_notes(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        if editing_policy(row)["bloopers_requested"]:
            continue
        for key, (pattern, _directive) in NOTE_RULES.items():
            allowed = {
                "clean_pauses": {"edit", "story", "pacing"},
                "product_referents": {"edit", "story"},
                "purposeful_variety": {"edit", "effects"},
                "safe_captions": {"edit", "captions"},
            }
            if row.get("scope", "edit") not in allowed[key]:
                continue
            if re.search(pattern, str(row.get("note") or ""), re.I):
                grouped[
                    (str(row["recipe"]), str(row.get("edit_style") or "clean"), key)
                ].append(row)
    proposals = []
    for (recipe, style, key), samples in grouped.items():
        # Revisions of one job cannot manufacture evidence for a global lesson.
        jobs = sorted({str(row["job_id"]) for row in samples})
        if len(jobs) < 3:
            continue
        proposals.append(
            {
                "id": uuid5(NAMESPACE_URL, f"gm-studio:lesson:{recipe}:{style}:{key}"),
                "recipe": recipe,
                "edit_style": style,
                "rule_key": key,
                "directive": NOTE_RULES[key][1],
                "feedback_ids": sorted({str(row["id"]) for row in samples}),
                "job_ids": jobs,
            }
        )
    return proposals


def source_hashes(database: Any, job_ids: list[str]) -> list[str]:
    return [
        row["sha256"] or ""
        for row in database.execute(
            "SELECT DISTINCT a.sha256 FROM job_assets j JOIN assets a ON a.id=j.asset_id WHERE j.job_id=ANY(%s::uuid[])",
            (job_ids,),
        ).fetchall()
    ]


def lesson(database: Any, lesson_id: UUID, *, lock=False):
    row = database.execute(
        "SELECT * FROM learning_lessons WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (lesson_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="lesson not found")
    return row


JOBS_SQL = """SELECT DISTINCT ON(j.id) j.id,p.name,j.recipe,j.edit_style,j.reel_intent,j.story_goal,
    j.must_include,j.ending_instruction,p.brief,p.privacy_mode,r.version,r.evaluation_lesson_id,r.status,r.preview_path,
    ARRAY(SELECT DISTINCT a.sha256 FROM job_assets ja JOIN assets a ON a.id=ja.asset_id WHERE ja.job_id=j.id) AS source_hashes,
    EXISTS(SELECT 1 FROM edit_runs active WHERE active.job_id=j.id AND active.status IN ('pending','planning','rendering')) AS busy
    FROM jobs j JOIN projects p ON p.id=j.project_id JOIN edit_runs r ON r.job_id=j.id
    WHERE r.status='ready' AND j.archived_at IS NULL AND p.name !~* '^Phase[[:space:]]+[0-9]'
    ORDER BY j.id,r.version DESC LIMIT 100"""

TRIAL_SOURCES_SQL = """SELECT DISTINCT r.evaluation_lesson_id,r.job_id,a.sha256
    FROM edit_runs r JOIN job_assets ja ON ja.job_id=r.job_id JOIN assets a ON a.id=ja.asset_id
    WHERE r.evaluation_lesson_id=ANY(%s::uuid[])"""


def trial_block_reason(item, job, previous):
    if editing_policy(job)["bloopers_requested"] or str(job["recipe"]) != item["recipe"] or str(job["edit_style"]) != item["edit_style"]:
        return "Choose a non-blooper job matching this lesson recipe and style; clean-take lessons do not apply to outtakes."
    identity = str(job.get("id") or job.get("job_id"))
    if identity in item["training_job_ids"] or set(job.get("source_hashes") or []) & set(item["training_source_hashes"]):
        return "Training footage is excluded; choose fresh recordings."
    if not known_hashes(job.get("source_hashes")) or not known_hashes(item["training_source_hashes"]):
        return "Source checksums are incomplete; independence cannot be checked yet."
    if any(str(row["job_id"]) == identity for row in previous):
        return "This job already has a trial for this lesson; review that comparison."
    if set(job["source_hashes"]) & {row["sha256"] for row in previous}:
        return "Footage overlaps another trial for this lesson; choose a different recording."
    if job.get("evaluation_lesson_id"):
        return "Choose an ordinary edit as the baseline, not another lesson trial."
    if job.get("privacy_mode") == "local_only":
        return "This job is local-only and cannot request an editor-model trial."
    if job.get("busy"):
        return "This job has an edit in progress."
    return None


@router.get("")
def lab():
    media_root = get_settings().media_root
    with connection() as database:
        lessons = list(
            database.execute(
                "SELECT * FROM learning_lessons ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        )
        evaluations = list(
            database.execute(
                """SELECT id,lesson_id,job_id,baseline_run_id,candidate_run_id,baseline_rating,candidate_rating,
                note,reviewer,created_at,updated_at,evidence FROM learning_evaluations
                WHERE lesson_id=ANY(%s::uuid[]) ORDER BY created_at DESC""",
                ([item["id"] for item in lessons],),
            ).fetchall()
        )
        trials = list(
            database.execute("""SELECT r.id,r.job_id,r.version,r.status,r.preview_path,r.evaluation_lesson_id,r.evaluation_case_id,r.based_on_run_id,b.version AS baseline_version,
            b.status AS baseline_status,b.preview_path AS baseline_path,p.name AS project_name,
            b.provider AS baseline_provider,r.provider AS candidate_provider,
            b.manifest->'quality_review'->>'status' AS baseline_quality,r.manifest->'quality_review'->>'status' AS candidate_quality,
            CASE WHEN saved.id IS NOT NULL THEN jsonb_build_object('id',saved.id,'label',saved.label,'category',saved.category,
                'expectations',saved.expectations,'max_candidate_tokens',saved.max_candidate_tokens) END AS test_case
            FROM edit_runs r JOIN edit_runs b ON b.id=r.based_on_run_id JOIN jobs j ON j.id=r.job_id JOIN projects p ON p.id=j.project_id
            LEFT JOIN learning_cases saved ON saved.id=r.evaluation_case_id
            WHERE r.evaluation_lesson_id IS NOT NULL ORDER BY r.created_at DESC LIMIT 100""").fetchall()
        )
        jobs = list(database.execute(JOBS_SQL).fetchall())
        previous = list(database.execute(TRIAL_SOURCES_SQL, ([item["id"] for item in lessons],)).fetchall())
        usage = usage_for_runs(database, list({identity for trial in trials for identity in (trial["id"],trial["based_on_run_id"])}))
        from app.learning_cases import CASES_SQL
        cases = list(database.execute(CASES_SQL).fetchall())
        history = list(database.execute("SELECT * FROM learning_lesson_events ORDER BY created_at DESC,id LIMIT 100").fetchall())
    for item in lessons:
        scored = [e for e in evaluations if e["lesson_id"] == item["id"]]
        item["evaluation"] = with_trial_readiness(evaluation_result(scored,item=item),item,
            [trial for trial in trials if trial["evaluation_lesson_id"] == item["id"]],scored)
        item["trial_options"] = []
        for job in jobs:
            if str(job["recipe"]) != item["recipe"] or str(job["edit_style"]) != item["edit_style"]:
                continue
            reason = trial_block_reason(item, job, [row for row in previous if row["evaluation_lesson_id"] == item["id"]])
            if not reason and not preview_available(job, media_root):
                reason = "The exact baseline preview has expired or is unavailable."
            item["trial_options"].append({"job_id": str(job["id"]), "eligible": reason is None, "reason": reason})
        item["case_options"] = []
        for case in cases:
            if str(case["recipe"]) != item["recipe"] or str(case["edit_style"]) != item["edit_style"]:
                continue
            task = {**case,"id":case["job_id"],"source_hashes":[source["sha256"] for source in case["sources"]]}
            reason = trial_block_reason(item,task,[row for row in previous if row["evaluation_lesson_id"] == item["id"]])
            if case["archived_at"] or case["job_archived_at"]:
                reason = "Restore the saved case and its job before starting a trial."
            elif not preview_available(case,media_root):
                reason = "The saved baseline preview is unavailable."
            item["case_options"].append({"case_id":str(case["id"]),"eligible":reason is None,"reason":reason})
    for trial in trials:
        trial["baseline_available"] = preview_available({"status":trial.pop("baseline_status"),"preview_path":trial.pop("baseline_path")},media_root)
        trial["candidate_available"] = preview_available(trial,media_root)
        trial.pop("preview_path",None)
        trial["baseline_usage"] = usage_snapshot({"provider":trial.get("baseline_provider")},usage.get(str(trial["based_on_run_id"])))
        trial["candidate_usage"] = usage_snapshot({"provider":trial.get("candidate_provider")},usage.get(str(trial["id"])))
        saved = next((e for e in evaluations if e["candidate_run_id"] == trial["id"]),None)
        trial["comparison"] = {**{key:saved[key] for key in ("baseline_rating","candidate_rating","note")},
            "rubric":(saved.get("evidence") or {}).get("rubric")} if saved else None
        trial["executable_changed"] = (saved.get("evidence") or {}).get("executable_changed") if saved else None
        case = next((case for case in cases if case["id"] == trial.get("evaluation_case_id")),None)
        trial["test_case"] = {key:case[key] for key in ("id","label","category","expectations","max_candidate_tokens")} if case else trial.get("test_case")
    for case in cases:
        case["baseline_available"] = preview_available(case,media_root)
        case["source_count"] = len(case.pop("sources"))
        case.pop("preview_path",None)
    return {
        "version": 3,
        "cases":cases,"history":history,
        "lessons": lessons,
        "evaluations": evaluations,
        "trials": trials,
        "jobs": [{**{key:job[key] for key in ("id","name","recipe","edit_style","version")},
            "ordinary":not bool(job.get("evaluation_lesson_id"))} for job in jobs],
        "hosted_model_calls": 0,
        "note": "Proposals and scoring run locally. Trying a lesson is an explicit normal editor revision and uses model tokens. Promotion never changes model weights or application code.",
    }


@router.post("/propose")
def propose(x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        rows = list(
            database.execute("""SELECT f.id,f.job_id,f.note,f.scope,j.recipe,j.edit_style,j.reel_intent,
            j.story_goal,j.must_include,j.ending_instruction,p.brief,p.name AS project_name FROM edit_feedback f
            JOIN jobs j ON j.id=f.job_id JOIN projects p ON p.id=j.project_id
            WHERE btrim(f.note)<>'' AND p.name !~* '^Phase[[:space:]]+[0-9]'
            ORDER BY f.updated_at DESC LIMIT 500""").fetchall()
        )
        proposals = propose_from_notes(rows)
        for item in proposals:
            hashes = source_hashes(database, item["job_ids"])
            if not known_hashes(hashes):
                continue
            database.execute(
                """INSERT INTO learning_lessons(id,recipe,edit_style,rule_key,directive,training_feedback_ids,training_job_ids,training_source_hashes)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(recipe,edit_style,rule_key) DO NOTHING""",
                (
                    item["id"],
                    item["recipe"],
                    item["edit_style"],
                    item["rule_key"],
                    item["directive"],
                    Jsonb(item["feedback_ids"]),
                    Jsonb(item["job_ids"]),
                    Jsonb(hashes),
                ),
            )
    return {"matched_proposals": len(proposals), "hosted_model_calls": 0}


class TrialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    base_version: int = Field(gt=0)
    case_id: UUID | None = None


def assert_holdout(database: Any, item: dict, job_id: UUID, *, scoring=False):
    job = database.execute(
        """SELECT j.recipe,j.edit_style,j.reel_intent,j.story_goal,j.must_include,j.ending_instruction,
        j.archived_at,p.brief,p.privacy_mode,p.name AS project_name FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=%s""", (job_id,)
    ).fetchone()
    if not job or job.get("archived_at"):
        raise HTTPException(409,"choose an active job for the lesson trial")
    job = {**job,"id":str(job_id),"source_hashes":source_hashes(database,[str(job_id)])}
    # New experiments must use fresh footage. Existing pairs can be rerated;
    # source-group aggregation still prevents legacy overlaps adding evidence.
    previous = [] if scoring else list(database.execute(TRIAL_SOURCES_SQL, ([item["id"]],)).fetchall())
    # Rechecking a finished comparison must allow that trial's own job.
    previous = [row for row in previous if str(row["job_id"]) != str(job_id)]
    reason = trial_block_reason(item,job,previous)
    if reason:
        raise HTTPException(409,reason)


@router.post("/lessons/{lesson_id}/trial")
def trial(
    lesson_id: UUID,
    payload: TrialRequest,
    x_gm_user_login: str | None = Header(default=None),
):
    require_owner(actor_login(x_gm_user_login))
    from app.editing import request_revision
    from app.schemas import RevisionCreate

    return request_revision(
        payload.job_id,
        RevisionCreate(
            base_version=payload.base_version, evaluation_lesson_id=lesson_id, evaluation_case_id=payload.case_id
        ),
    )


class PlaybackRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief: Literal["better", "same", "worse", "not_applicable"]
    story: Literal["better", "same", "worse", "not_applicable"]
    speech: Literal["better", "same", "worse", "not_applicable"]
    captions: Literal["better", "same", "worse", "not_applicable"]
    visuals: Literal["better", "same", "worse", "not_applicable"]
    audio: Literal["better", "same", "worse", "not_applicable"]


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_run_id: UUID
    baseline_rating: int = Field(ge=1, le=5)
    candidate_rating: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=1200)
    rubric: PlaybackRubric | None = None
    reviewed_both: bool = False


@router.post("/lessons/{lesson_id}/evaluate")
def evaluate(
    lesson_id: UUID,
    payload: EvaluationCreate,
    x_gm_user_login: str | None = Header(default=None),
):
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    with connection() as database:
        item = lesson(database, lesson_id, lock=True)
        candidate = database.execute(
            "SELECT * FROM edit_runs WHERE id=%s AND status='ready' AND evaluation_lesson_id=%s",
            (payload.candidate_run_id, lesson_id),
        ).fetchone()
        if not candidate or not candidate["based_on_run_id"]:
            raise HTTPException(
                status_code=409,
                detail="evaluate a finished trial preview created for this lesson",
            )
        if candidate.get("revision_note") != item["directive"]:
            raise HTTPException(409,"the trial used a different lesson directive; compare the matching lesson version")
        baseline = database.execute(
            "SELECT * FROM edit_runs WHERE id=%s AND status='ready' AND job_id=%s",
            (candidate["based_on_run_id"], candidate["job_id"]),
        ).fetchone()
        if not baseline:
            raise HTTPException(
                status_code=409, detail="the trial baseline is unavailable"
            )
        assert_holdout(database, item, candidate["job_id"], scoring=True)
        case = None
        if candidate.get("evaluation_case_id"):
            from app.learning_cases import assert_case
            case = assert_case(database,candidate["evaluation_case_id"],candidate["job_id"],baseline)
            if not payload.reviewed_both or payload.rubric is None:
                raise HTTPException(422, "review both exact previews and complete the playback checklist")
        elif item.get("evaluation_protocol", 1) >= 2:
            raise HTTPException(409, "this legacy trial has no saved test case; use a new independent saved-case trial")
        evidence = comparison_evidence(database,item,baseline,candidate,get_settings().media_root,**(
            {"case":case,"rubric":payload.rubric.model_dump(),"reviewed_both":True} if case else {}))
        database.execute(
            """INSERT INTO learning_evaluations(id,lesson_id,job_id,baseline_run_id,candidate_run_id,baseline_rating,candidate_rating,note,reviewer,evidence)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(lesson_id,job_id) DO UPDATE SET
            candidate_run_id=EXCLUDED.candidate_run_id,baseline_run_id=EXCLUDED.baseline_run_id,
            baseline_rating=EXCLUDED.baseline_rating,candidate_rating=EXCLUDED.candidate_rating,note=EXCLUDED.note,reviewer=EXCLUDED.reviewer,
            evidence=EXCLUDED.evidence,updated_at=now()""",
            (
                uuid4(),
                lesson_id,
                candidate["job_id"],
                baseline["id"],
                candidate["id"],
                payload.baseline_rating,
                payload.candidate_rating,
                payload.note,
                actor,
                Jsonb(evidence),
            ),
        )
        rows = list(
            database.execute(
                "SELECT * FROM learning_evaluations WHERE lesson_id=%s", (lesson_id,)
            ).fetchall()
        )
    return evaluation_result(rows,item=item)


class LessonAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["promote", "rollback", "upgrade"]


@router.post("/lessons/{lesson_id}/status")
def change_status(
    lesson_id: UUID,
    payload: LessonAction,
    x_gm_user_login: str | None = Header(default=None),
):
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    with connection() as database:
        item = lesson(database, lesson_id, lock=True)
        rows = list(
            database.execute(
                "SELECT * FROM learning_evaluations WHERE lesson_id=%s", (lesson_id,)
            ).fetchall()
        )
        report = with_trial_readiness(evaluation_result(rows,item=item),item,
            list(database.execute("SELECT id,status,evaluation_case_id FROM edit_runs WHERE evaluation_lesson_id=%s",(lesson_id,)).fetchall()),rows)
        if payload.action == "promote" and not report["can_promote"]:
            raise HTTPException(
                status_code=409,
                detail="this lesson has not passed held-out playback evaluation",
            )
        if payload.action == "upgrade" and item["status"] == "promoted":
            raise HTTPException(409, "roll back the active lesson before changing its evaluation protocol")
        state = "promoted" if payload.action == "promote" else "proposed" if payload.action == "upgrade" else "rolled_back"
        if (payload.action == "upgrade" and item.get("evaluation_protocol",1) >= 2) or (payload.action != "upgrade" and state == item["status"]):
            return {"id":str(lesson_id),"status":item["status"],"hosted_model_calls":0}
        version = int(item.get("deployment_version",0)) + 1
        database.execute(
            "UPDATE learning_lessons SET status=%s,deployment_version=%s,evaluation_protocol=%s,updated_at=now() WHERE id=%s",
            (state,version,2 if payload.action == "upgrade" else item.get("evaluation_protocol",1),lesson_id),
        )
        database.execute("""INSERT INTO learning_lesson_events(id,lesson_id,deployment_version,action,previous_status,
            status,directive_hash,actor,evaluation) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid4(),lesson_id,version,payload.action,item["status"],state,
             document_sha256({"directive":item["directive"]}),actor,Jsonb({**report,"case_ids":sorted({str((row.get("evidence") or {}).get("case_id")) for row in rows if (row.get("evidence") or {}).get("case_id")})})))
    return {"id": str(lesson_id), "status": state, "deployment_version":version,"hosted_model_calls": 0}
