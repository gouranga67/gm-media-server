from __future__ import annotations

import math
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from psycopg.types.json import Jsonb

from app.database import connection
from app.schemas import (
    EditFeedbackCreate,
    EditFeedbackResponse,
    LearningSettingsResponse,
    LearningSettingsUpdate,
    LearningSummaryResponse,
)


router = APIRouter(prefix="/api/v1", tags=["learning"])


FEEDBACK_RULES: dict[str, dict[str, str]] = {
    "effects_worked": {"dimension": "effects", "sentiment": "positive", "directive": "Keep creative effects sparse, purposeful, and synchronized to genuine story beats."},
    "effects_too_much": {"dimension": "effects", "sentiment": "negative", "directive": "Use fewer creative effects and reserve them for the strongest hook, reveal, reaction, or payoff."},
    "effects_too_loud": {"dimension": "effects_audio", "sentiment": "negative", "directive": "Reduce sound-effect intensity and protect speech intelligibility at every cue."},
    "effect_timing_issue": {"dimension": "effects_timing", "sentiment": "negative", "directive": "Place creative effects precisely on the source-backed beat they explain or emphasize."},
    "meme_worked": {"dimension": "memes", "sentiment": "positive", "directive": "Use a reviewed meme asset only when its meaning naturally reinforces the source moment."},
    "meme_forced": {"dimension": "memes", "sentiment": "negative", "directive": "Avoid meme assets unless the source moment clearly earns the reference."},
    "strong_hook": {
        "dimension": "hook",
        "sentiment": "positive",
        "directive": "Keep opening on the strongest source-backed hook with minimal setup.",
    },
    "weak_hook": {
        "dimension": "hook",
        "sentiment": "negative",
        "directive": "Reach the strongest source-backed hook sooner and remove routine opening setup.",
    },
    "clear_story": {
        "dimension": "story",
        "sentiment": "positive",
        "directive": "Preserve a clear setup, development, payoff, and ending.",
    },
    "confusing_story": {
        "dimension": "story",
        "sentiment": "negative",
        "directive": "Prioritize causal story order and include only context needed to understand the payoff.",
    },
    "pacing_too_slow": {
        "dimension": "pacing",
        "sentiment": "negative",
        "directive": "Use tighter pacing, remove dead air, and reach new information sooner while keeping complete phrases.",
    },
    "pacing_too_fast": {
        "dimension": "pacing",
        "sentiment": "negative",
        "directive": "Allow important phrases and reaction beats more time; avoid rapid cuts that reduce comprehension.",
    },
    "clean_captions": {
        "dimension": "captions",
        "sentiment": "positive",
        "directive": "Keep captions concise, synchronized, and limited to the words currently being spoken.",
    },
    "caption_issue": {
        "dimension": "captions",
        "sentiment": "negative",
        "directive": "Protect speech boundaries and keep caption events short and synchronized to spoken phrases.",
    },
    "balanced_audio": {
        "dimension": "audio",
        "sentiment": "positive",
        "directive": "Preserve clear speech with restrained music ducked beneath dialogue.",
    },
    "audio_issue": {
        "dimension": "audio",
        "sentiment": "negative",
        "directive": "Prioritize intelligible speech, consistent source levels, and clearly audible but subordinate music.",
    },
    "good_visuals": {
        "dimension": "visuals",
        "sentiment": "positive",
        "directive": "Keep purposeful visual variety tied to genuine emphasis and story beats.",
    },
    "visual_issue": {
        "dimension": "visuals",
        "sentiment": "negative",
        "directive": "Choose clearer source moments and use restrained reframing only when it supports the story.",
    },
    "good_colour": {
        "dimension": "colour",
        "sentiment": "positive",
        "directive": "Preserve natural skin tones, contrast, and source colour intent.",
    },
    "colour_issue": {
        "dimension": "colour",
        "sentiment": "negative",
        "directive": "Favor naturally exposed source moments and avoid shots with visibly degraded colour or contrast.",
    },
    "strong_ending": {
        "dimension": "ending",
        "sentiment": "positive",
        "directive": "Finish on the clearest supported conclusion or call to action.",
    },
    "weak_ending": {
        "dimension": "ending",
        "sentiment": "negative",
        "directive": "Build to a distinct source-backed ending instead of stopping on an unfinished thought.",
    },
}


def derive_learning_preferences(
    feedback: list[dict[str, Any]],
    *,
    minimum_samples: int = 3,
) -> dict[str, Any]:
    """Turn repeated explicit feedback into bounded, explainable directives."""

    sample_size = len(feedback)
    ratings = [int(row["rating"]) for row in feedback]
    tag_counts: dict[str, int] = defaultdict(int)
    for row in feedback:
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        for tag in set(str(item) for item in tags):
            if tag in FEEDBACK_RULES:
                tag_counts[tag] += 1

    threshold = max(2, math.ceil(sample_size * 0.34))
    candidates: list[dict[str, Any]] = []
    if sample_size >= minimum_samples:
        for tag, count in tag_counts.items():
            if count < threshold:
                continue
            rule = FEEDBACK_RULES[tag]
            candidates.append(
                {
                    "tag": tag,
                    "dimension": rule["dimension"],
                    "sentiment": rule["sentiment"],
                    "directive": rule["directive"],
                    "evidence_count": count,
                    "sample_size": sample_size,
                    "confidence": round(count / sample_size, 3),
                }
            )

    # Conflicting feedback in one dimension never becomes two instructions.
    # Keep the best-supported rule, and require a clear winner on equal counts.
    by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_dimension[candidate["dimension"]].append(candidate)
    active: list[dict[str, Any]] = []
    for dimension_candidates in by_dimension.values():
        ordered = sorted(
            dimension_candidates,
            key=lambda item: (item["evidence_count"], item["confidence"], item["tag"]),
            reverse=True,
        )
        if len(ordered) > 1 and ordered[0]["evidence_count"] == ordered[1]["evidence_count"]:
            continue
        active.append(ordered[0])
    active.sort(key=lambda item: (-item["confidence"], item["dimension"]))

    return {
        "sample_size": sample_size,
        "minimum_samples": minimum_samples,
        "average_rating": round(sum(ratings) / sample_size, 2) if ratings else None,
        "feedback_needed": max(0, minimum_samples - sample_size),
        "preferences": active,
    }


def _settings(database: Any) -> dict[str, Any]:
    row = database.execute("SELECT * FROM learning_settings WHERE id=1").fetchone()
    if row is None:
        raise RuntimeError("learning settings are missing")
    return row


def learning_context_for_job(database: Any, job: dict[str, Any]) -> dict[str, Any]:
    settings = _settings(database)
    if not settings["enabled"]:
        return {
            "enabled": False,
            "sample_size": 0,
            "preferences": [],
            "hosted_model_calls": 0,
        }
    rows = database.execute(
        """
        SELECT edit_feedback.rating, edit_feedback.tags
        FROM edit_feedback
        JOIN jobs ON jobs.id = edit_feedback.job_id
        JOIN projects ON projects.id = jobs.project_id
        WHERE jobs.recipe = %s
          AND projects.name !~* '^Phase[[:space:]]+[0-9]+[A-Z]*[[:space:]]+(library[[:space:]]+)?verification'
        ORDER BY edit_feedback.updated_at DESC
        LIMIT 100
        """,
        (job["recipe"],),
    ).fetchall()
    learned = derive_learning_preferences(
        list(rows), minimum_samples=int(settings["minimum_samples"])
    )
    return {
        "enabled": True,
        "scope": str(job["recipe"]),
        **learned,
        "directives": [item["directive"] for item in learned["preferences"]],
        "source": "local_explicit_feedback",
        "hosted_model_calls": 0,
    }


def _feedback_response(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


@router.post(
    "/jobs/{job_id}/feedback",
    response_model=EditFeedbackResponse,
    status_code=status.HTTP_200_OK,
)
def save_edit_feedback(job_id: UUID, payload: EditFeedbackCreate) -> dict[str, Any]:
    with connection() as database:
        run = database.execute(
            "SELECT id, status FROM edit_runs WHERE id=%s AND job_id=%s",
            (payload.edit_run_id, job_id),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="edit version not found")
        if run["status"] != "ready":
            raise HTTPException(status_code=409, detail="feedback requires a finished preview")
        row = database.execute(
            """
            INSERT INTO edit_feedback (
                job_id, edit_run_id, rating, tags, note, would_use_again
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (edit_run_id) DO UPDATE SET
                rating=excluded.rating, tags=excluded.tags, note=excluded.note,
                would_use_again=excluded.would_use_again, updated_at=now()
            RETURNING *
            """,
            (
                job_id,
                payload.edit_run_id,
                payload.rating,
                Jsonb(payload.tags),
                payload.note,
                payload.would_use_again,
            ),
        ).fetchone()
        database.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload)
            VALUES (%s, 'edit_feedback_saved', %s)
            """,
            (job_id, Jsonb({"edit_run_id": str(payload.edit_run_id), "rating": payload.rating})),
        )
    assert row is not None
    return _feedback_response(row)


@router.delete("/jobs/{job_id}/feedback/{edit_run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edit_feedback(job_id: UUID, edit_run_id: UUID) -> None:
    with connection() as database:
        deleted = database.execute(
            "DELETE FROM edit_feedback WHERE job_id=%s AND edit_run_id=%s",
            (job_id, edit_run_id),
        )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="feedback not found")


@router.get("/learning/summary", response_model=LearningSummaryResponse)
def learning_summary() -> dict[str, Any]:
    with connection() as database:
        settings = _settings(database)
        rows = database.execute(
            """
            SELECT edit_feedback.*, jobs.recipe, jobs.edit_style, jobs.music_mode,
                   edit_runs.version, projects.name AS project_name
            FROM edit_feedback
            JOIN jobs ON jobs.id = edit_feedback.job_id
            JOIN edit_runs ON edit_runs.id = edit_feedback.edit_run_id
            JOIN projects ON projects.id = jobs.project_id
            WHERE projects.name !~* '^Phase[[:space:]]+[0-9]+[A-Z]*[[:space:]]+(library[[:space:]]+)?verification'
            ORDER BY edit_feedback.updated_at DESC
            LIMIT 250
            """
        ).fetchall()
        outcomes = database.execute(
            """
            SELECT count(*) FILTER (WHERE final_exports.status='ready') AS delivered_jobs,
                   count(*) FILTER (WHERE edit_runs.version=1 AND edit_runs.approved_at IS NOT NULL)
                       AS first_pass_approvals,
                   count(*) FILTER (WHERE edit_runs.approved_at IS NOT NULL) AS approvals
            FROM edit_runs
            LEFT JOIN final_exports ON final_exports.edit_run_id=edit_runs.id
            """
        ).fetchone()
    minimum = int(settings["minimum_samples"])
    all_feedback = list(rows)
    scopes = {
        "all": derive_learning_preferences(all_feedback, minimum_samples=minimum),
        "talking_head": derive_learning_preferences(
            [row for row in all_feedback if row["recipe"] == "talking_head"],
            minimum_samples=minimum,
        ),
        "montage": derive_learning_preferences(
            [row for row in all_feedback if row["recipe"] == "montage"],
            minimum_samples=minimum,
        ),
    }
    approvals = int(outcomes["approvals"] or 0) if outcomes else 0
    first_pass = int(outcomes["first_pass_approvals"] or 0) if outcomes else 0
    return {
        "settings": settings,
        "feedback_count": len(all_feedback),
        "average_rating": scopes["all"]["average_rating"],
        "would_use_again_count": sum(bool(row["would_use_again"]) for row in all_feedback),
        "delivered_jobs": int(outcomes["delivered_jobs"] or 0) if outcomes else 0,
        "first_pass_approval_rate": round(first_pass / approvals, 3) if approvals else None,
        "scopes": scopes,
        "recent_feedback": all_feedback[:20],
        "hosted_model_calls": 0,
    }


@router.put("/learning/settings", response_model=LearningSettingsResponse)
def update_learning_settings(payload: LearningSettingsUpdate) -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            """
            UPDATE learning_settings
            SET enabled=%s, minimum_samples=%s, updated_at=now()
            WHERE id=1 RETURNING *
            """,
            (payload.enabled, payload.minimum_samples),
        ).fetchone()
    assert row is not None
    return row
