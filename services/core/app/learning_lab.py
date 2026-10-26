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


def evaluation_result(rows: list[dict]) -> dict:
    jobs = {str(row["job_id"]) for row in rows}
    deltas = [
        int(row["candidate_rating"]) - int(row["baseline_rating"]) for row in rows
    ]
    passed = len(jobs) >= 3 and all(delta >= 0 for delta in deltas) and sum(deltas) > 0
    return {
        "held_out_jobs": len(jobs),
        "rating_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "regressions": sum(delta < 0 for delta in deltas),
        "can_promote": passed,
        "method": "human paired playback review; distinct jobs and source hashes",
        "note": "Three independent held-out jobs, no lower rating, and at least one improvement are required. This is not proof of universal quality.",
    }


def source_hashes(database: Any, job_ids: list[str]) -> list[str]:
    return [
        row["sha256"]
        for row in database.execute(
            "SELECT DISTINCT a.sha256 FROM job_assets j JOIN assets a ON a.id=j.asset_id WHERE j.job_id=ANY(%s::uuid[]) AND a.sha256 IS NOT NULL",
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


@router.get("")
def lab():
    with connection() as database:
        lessons = list(
            database.execute(
                "SELECT * FROM learning_lessons ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        )
        evaluations = list(
            database.execute(
                "SELECT * FROM learning_evaluations ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        )
        trials = list(
            database.execute("""SELECT r.id,r.job_id,r.version,r.status,r.evaluation_lesson_id,r.based_on_run_id,b.version AS baseline_version,p.name AS project_name
            FROM edit_runs r JOIN edit_runs b ON b.id=r.based_on_run_id JOIN jobs j ON j.id=r.job_id JOIN projects p ON p.id=j.project_id
            WHERE r.evaluation_lesson_id IS NOT NULL ORDER BY r.created_at DESC LIMIT 100""").fetchall()
        )
        jobs = list(
            database.execute("""SELECT DISTINCT ON(j.id) j.id,p.name,j.recipe,j.edit_style,r.version
            FROM jobs j JOIN projects p ON p.id=j.project_id JOIN edit_runs r ON r.job_id=j.id
            WHERE r.status='ready' AND j.archived_at IS NULL AND p.name !~* '^Phase[[:space:]]+[0-9]'
            ORDER BY j.id,r.version DESC LIMIT 100""").fetchall()
        )
    for item in lessons:
        item["evaluation"] = evaluation_result(
            [e for e in evaluations if e["lesson_id"] == item["id"]]
        )
    return {
        "lessons": lessons,
        "evaluations": evaluations,
        "trials": trials,
        "jobs": jobs,
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
                    Jsonb(source_hashes(database, item["job_ids"])),
                ),
            )
    return {"matched_proposals": len(proposals), "hosted_model_calls": 0}


class TrialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    base_version: int = Field(gt=0)


def assert_holdout(database: Any, item: dict, job_id: UUID):
    if str(job_id) in item["training_job_ids"] or set(
        source_hashes(database, [str(job_id)])
    ) & set(item["training_source_hashes"]):
        raise HTTPException(
            status_code=409,
            detail="use a job with footage not used to propose this lesson; training sources are excluded from held-out evaluation",
        )
    job = database.execute(
        """SELECT j.recipe,j.edit_style,j.reel_intent,j.story_goal,j.must_include,j.ending_instruction,
        p.brief,p.name AS project_name FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=%s""", (job_id,)
    ).fetchone()
    if (
        not job
        or editing_policy(job)["bloopers_requested"]
        or str(job["recipe"]) != item["recipe"]
        or str(job["edit_style"]) != item["edit_style"]
    ):
        raise HTTPException(
            status_code=409, detail="choose a non-blooper job matching this lesson recipe and style; clean-take lessons do not apply to outtakes"
        )


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
            base_version=payload.base_version, evaluation_lesson_id=lesson_id
        ),
    )


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_run_id: UUID
    baseline_rating: int = Field(ge=1, le=5)
    candidate_rating: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=1200)


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
        baseline = database.execute(
            "SELECT * FROM edit_runs WHERE id=%s AND status='ready' AND job_id=%s",
            (candidate["based_on_run_id"], candidate["job_id"]),
        ).fetchone()
        if not baseline:
            raise HTTPException(
                status_code=409, detail="the trial baseline is unavailable"
            )
        assert_holdout(database, item, candidate["job_id"])
        database.execute(
            """INSERT INTO learning_evaluations(id,lesson_id,job_id,baseline_run_id,candidate_run_id,baseline_rating,candidate_rating,note,reviewer)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(lesson_id,job_id) DO UPDATE SET
            candidate_run_id=EXCLUDED.candidate_run_id,baseline_run_id=EXCLUDED.baseline_run_id,
            baseline_rating=EXCLUDED.baseline_rating,candidate_rating=EXCLUDED.candidate_rating,note=EXCLUDED.note,reviewer=EXCLUDED.reviewer""",
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
            ),
        )
        rows = list(
            database.execute(
                "SELECT * FROM learning_evaluations WHERE lesson_id=%s", (lesson_id,)
            ).fetchall()
        )
    return evaluation_result(rows)


class LessonAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["promote", "rollback"]


@router.post("/lessons/{lesson_id}/status")
def change_status(
    lesson_id: UUID,
    payload: LessonAction,
    x_gm_user_login: str | None = Header(default=None),
):
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        lesson(database, lesson_id, lock=True)
        rows = list(
            database.execute(
                "SELECT * FROM learning_evaluations WHERE lesson_id=%s", (lesson_id,)
            ).fetchall()
        )
        if payload.action == "promote" and not evaluation_result(rows)["can_promote"]:
            raise HTTPException(
                status_code=409,
                detail="this lesson has not passed held-out playback evaluation",
            )
        state = "promoted" if payload.action == "promote" else "rolled_back"
        database.execute(
            "UPDATE learning_lessons SET status=%s,updated_at=now() WHERE id=%s",
            (state, lesson_id),
        )
    return {"id": str(lesson_id), "status": state, "hosted_model_calls": 0}
