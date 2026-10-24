from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.database import connection
from app.media_analysis import resolve_source


router = APIRouter(prefix="/api/v1", tags=["productization"])


def normalize_login(value: str) -> str:
    return value.strip().lower()


def actor_login(header: str | None) -> str:
    return normalize_login(header or get_settings().tailscale_owner_login or "system")


def ensure_owner(database: Any) -> dict[str, Any] | None:
    owner = normalize_login(get_settings().tailscale_owner_login)
    if not owner:
        return None
    database.execute(
        """
        UPDATE studio_members SET role='editor', active=false, updated_at=now()
        WHERE role='owner' AND login<>%s
        """,
        (owner,),
    )
    database.execute(
        """
        INSERT INTO studio_members (login, display_name, role)
        VALUES (%s, %s, 'owner')
        ON CONFLICT (login) DO UPDATE SET role='owner', active=true, updated_at=now()
        """,
        (owner, owner.split("@", 1)[0]),
    )
    return database.execute("SELECT * FROM studio_members WHERE login=%s", (owner,)).fetchone()


def require_owner(login: str) -> None:
    with connection() as database:
        ensure_owner(database)
        member = database.execute(
            "SELECT role, active FROM studio_members WHERE login=%s", (normalize_login(login),)
        ).fetchone()
    if member is None or not member["active"] or member["role"] != "owner":
        raise HTTPException(status_code=403, detail="owner access is required")


def require_editor(login: str) -> None:
    with connection() as database:
        ensure_owner(database)
        member = database.execute(
            "SELECT role, active FROM studio_members WHERE login=%s", (normalize_login(login),)
        ).fetchone()
    if member is None or not member["active"] or member["role"] not in {"owner", "editor"}:
        raise HTTPException(status_code=403, detail="editor access is required")


def authorize_login(login: str) -> dict[str, Any]:
    normalized = normalize_login(login)
    with connection() as database:
        ensure_owner(database)
        member = database.execute(
            "SELECT login, display_name, role, active FROM studio_members WHERE login=%s",
            (normalized,),
        ).fetchone()
    return {
        "authorized": bool(member and member["active"]),
        "member": member if member and member["active"] else None,
    }


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=120)
    role: Literal["editor", "viewer"]

    @field_validator("login")
    @classmethod
    def clean_login(cls, value: str) -> str:
        normalized = normalize_login(value)
        if "@" not in normalized or any(character.isspace() for character in normalized):
            raise ValueError("use the person's Tailscale login email")
        return normalized


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(default="", max_length=120)
    role: Literal["editor", "viewer"]
    active: bool = True


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    studio_name: str = Field(min_length=1, max_length=80)
    onboarding_completed: bool = False
    daily_ai_token_limit: int = Field(default=0, ge=0, le=100_000_000)
    monthly_ai_token_limit: int = Field(default=0, ge=0, le=2_000_000_000)
    max_active_jobs: int = Field(default=2, ge=1, le=20)
    preview_retention_days: int = Field(default=30, ge=1, le=3650)
    delivery_retention_days: int = Field(default=90, ge=1, le=3650)


def _audit(database: Any, actor: str, action: str, target_type: str = "", target_id: str = "", details: dict[str, Any] | None = None) -> None:
    database.execute(
        "INSERT INTO studio_audit_events (actor_login, action, target_type, target_id, details) VALUES (%s,%s,%s,%s,%s)",
        (actor, action, target_type, target_id, Jsonb(details or {})),
    )


@router.get("/access/authorize")
def access_authorize(
    login: str = Query(min_length=3, max_length=320),
    x_gm_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if x_gm_internal_token != get_settings().access_internal_secret:
        raise HTTPException(status_code=401, detail="invalid internal access token")
    return authorize_login(login)


@router.get("/members/me")
def current_member(x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    result = authorize_login(actor_login(x_gm_user_login))
    if not result["authorized"]:
        raise HTTPException(status_code=403, detail="this Tailscale identity has not been invited")
    return result["member"]


@router.get("/members")
def list_members(x_gm_user_login: str | None = Header(default=None)) -> list[dict[str, Any]]:
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        ensure_owner(database)
        return list(database.execute("SELECT * FROM studio_members ORDER BY role, lower(login)").fetchall())


@router.post("/members", status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreate, x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    try:
        with connection() as database:
            row = database.execute(
                "INSERT INTO studio_members (login, display_name, role) VALUES (%s,%s,%s) RETURNING *",
                (payload.login, payload.display_name.strip(), payload.role),
            ).fetchone()
            _audit(database, actor, "member.created", "member", payload.login, {"role": payload.role})
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="that Tailscale identity is already a member") from error
    assert row is not None
    return row


@router.put("/members/{login}")
def update_member(login: str, payload: MemberUpdate, x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    normalized = normalize_login(login)
    with connection() as database:
        existing = database.execute("SELECT role FROM studio_members WHERE login=%s", (normalized,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="member not found")
        if existing["role"] == "owner":
            raise HTTPException(status_code=409, detail="the appliance owner cannot be changed here")
        row = database.execute(
            "UPDATE studio_members SET display_name=%s, role=%s, active=%s, updated_at=now() WHERE login=%s RETURNING *",
            (payload.display_name.strip(), payload.role, payload.active, normalized),
        ).fetchone()
        _audit(database, actor, "member.updated", "member", normalized, {"role": payload.role, "active": payload.active})
    assert row is not None
    return row


@router.delete("/members/{login}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(login: str, x_gm_user_login: str | None = Header(default=None)) -> None:
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    normalized = normalize_login(login)
    with connection() as database:
        existing = database.execute("SELECT role FROM studio_members WHERE login=%s", (normalized,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="member not found")
        if existing["role"] == "owner":
            raise HTTPException(status_code=409, detail="the appliance owner cannot be removed")
        database.execute("DELETE FROM studio_members WHERE login=%s", (normalized,))
        _audit(database, actor, "member.deleted", "member", normalized)


def _settings(database: Any) -> dict[str, Any]:
    row = database.execute("SELECT * FROM studio_settings WHERE singleton=true").fetchone()
    assert row is not None
    return row


def _usage_window(database: Any) -> dict[str, int]:
    row = database.execute(
        """
        SELECT COALESCE(sum(total_tokens) FILTER (WHERE created_at >= date_trunc('day', now())),0) AS today,
               COALESCE(sum(total_tokens) FILTER (WHERE created_at >= date_trunc('month', now())),0) AS month
        FROM ai_usage_events
        """
    ).fetchone()
    assert row is not None
    return {"today": int(row["today"]), "month": int(row["month"])}


def ai_budget_status(database: Any | None = None) -> dict[str, Any]:
    if database is None:
        with connection() as owned:
            return ai_budget_status(owned)
    settings = _settings(database)
    usage = _usage_window(database)
    daily = int(settings["daily_ai_token_limit"])
    monthly = int(settings["monthly_ai_token_limit"])
    allowed = (daily == 0 or usage["today"] < daily) and (monthly == 0 or usage["month"] < monthly)
    return {"allowed": allowed, "today_tokens": usage["today"], "month_tokens": usage["month"], "daily_limit": daily, "monthly_limit": monthly}


def assert_ai_budget(database: Any | None = None) -> None:
    budget = ai_budget_status(database)
    if not budget["allowed"]:
        raise RuntimeError("AI usage limit reached; the owner can raise the limit in Operations")


def assert_job_capacity(database: Any, job_id: UUID) -> None:
    configured = _settings(database)
    active = database.execute(
        """
        SELECT count(*) AS count FROM jobs
        WHERE id <> %s AND status IN (
          'uploading','ingesting','analyzing','planning','previewing','revising','exporting','rendering'
        )
        """,
        (job_id,),
    ).fetchone()
    if int((active or {"count": 0})["count"]) >= int(configured["max_active_jobs"]):
        raise HTTPException(
            status_code=429,
            detail="the studio has reached its active-job limit; wait for a current job or raise the limit in Operations",
        )


@router.get("/studio/settings")
def get_studio_settings() -> dict[str, Any]:
    with connection() as database:
        settings = _settings(database)
        budget = ai_budget_status(database)
    return {**settings, "budget": budget}


@router.put("/studio/settings")
def update_studio_settings(payload: SettingsUpdate, x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    with connection() as database:
        row = database.execute(
            """
            UPDATE studio_settings SET studio_name=%s, onboarding_completed=%s,
                daily_ai_token_limit=%s, monthly_ai_token_limit=%s, max_active_jobs=%s,
                preview_retention_days=%s, delivery_retention_days=%s, updated_at=now()
            WHERE singleton=true RETURNING *
            """,
            (payload.studio_name.strip(), payload.onboarding_completed, payload.daily_ai_token_limit,
             payload.monthly_ai_token_limit, payload.max_active_jobs, payload.preview_retention_days,
             payload.delivery_retention_days),
        ).fetchone()
        _audit(database, actor, "settings.updated", "studio", "primary")
        budget = ai_budget_status(database)
    assert row is not None
    return {**row, "budget": budget}


def _storage_totals(database: Any) -> dict[str, int]:
    originals = database.execute(
        "SELECT COALESCE(sum(byte_size),0) AS logical, COALESCE(sum(size),0) AS physical FROM (SELECT byte_size, CASE WHEN row_number() OVER (PARTITION BY sha256 ORDER BY created_at)=1 THEN byte_size ELSE 0 END AS size FROM assets WHERE status='ready') q"
    ).fetchone()
    preview_rows = database.execute(
        "SELECT preview_path, manifest_path FROM edit_runs WHERE preview_path IS NOT NULL OR manifest_path IS NOT NULL"
    ).fetchall()
    delivery_rows = database.execute(
        """
        SELECT video_path, captions_path, cover_path, post_copy_path, package_path, manifest_path FROM final_exports
        UNION ALL
        SELECT video_path, captions_path, cover_path, post_copy_path, package_path, manifest_path FROM delivery_variants
        """
    ).fetchall()
    media_root = get_settings().media_root

    def stored_bytes(rows: list[dict[str, Any]]) -> int:
        total = 0
        visited: set[str] = set()
        for row in rows:
            for value in row.values():
                if not value or str(value) in visited:
                    continue
                visited.add(str(value))
                try:
                    total += resolve_source(media_root, str(value)).stat().st_size
                except (FileNotFoundError, OSError, ValueError):
                    continue
        return total

    assert originals is not None
    return {"original_logical_bytes": int(originals["logical"]), "original_physical_estimate_bytes": int(originals["physical"]), "preview_estimate_bytes": stored_bytes(list(preview_rows)), "delivery_estimate_bytes": stored_bytes(list(delivery_rows))}


def _retention_candidates(database: Any, settings: dict[str, Any]) -> dict[str, Any]:
    preview = database.execute(
        "SELECT count(*) AS records FROM edit_runs WHERE preview_path IS NOT NULL AND completed_at < now() - (%s * interval '1 day')",
        (settings["preview_retention_days"],),
    ).fetchone()
    delivery = database.execute(
        """
        SELECT (SELECT count(*) FROM final_exports WHERE package_path IS NOT NULL AND completed_at < now() - (%s * interval '1 day')) +
               (SELECT count(*) FROM delivery_variants WHERE package_path IS NOT NULL AND completed_at < now() - (%s * interval '1 day')) AS records
        """,
        (settings["delivery_retention_days"], settings["delivery_retention_days"]),
    ).fetchone()
    return {"preview_records": int((preview or {"records": 0})["records"]), "delivery_records": int((delivery or {"records": 0})["records"]), "originals_eligible": 0}


@router.get("/studio/overview")
def studio_overview() -> dict[str, Any]:
    settings = get_settings()
    with connection() as database:
        ensure_owner(database)
        configuration = _settings(database)
        counts = database.execute(
            """SELECT (SELECT count(*) FROM projects) AS projects,
                      (SELECT count(*) FROM jobs WHERE archived_at IS NULL) AS jobs,
                      (SELECT count(*) FROM assets WHERE status='ready') AS assets,
                      (SELECT count(*) FROM final_exports WHERE status='ready') AS deliveries,
                      (SELECT count(*) FROM brand_kits) AS brand_kits,
                      (SELECT count(*) FROM music_tracks) AS music_tracks,
                      (SELECT count(*) FROM editor_models WHERE available=true) AS editor_models"""
        ).fetchone()
        members = database.execute("SELECT count(*) AS count FROM studio_members WHERE active=true").fetchone()
        active = database.execute(
            """
            SELECT count(*) AS count FROM jobs
            WHERE archived_at IS NULL AND status IN (
              'uploading','ingesting','analyzing','planning','previewing','revising','exporting','rendering'
            )
            """
        ).fetchone()
        budget = ai_budget_status(database)
        storage = _storage_totals(database)
        retention = _retention_candidates(database, configuration)
    health_ready = False
    try:
        health_ready = get_settings().appliance_status_path.exists()
    except OSError:
        pass
    return {
        "settings": configuration,
        "counts": {**(counts or {}), "members": int((members or {"count": 0})["count"]), "active_jobs": int((active or {"count": 0})["count"])},
        "budget": budget,
        "storage": storage,
        "retention": retention,
        "readiness": {
            "private_access": bool(settings.tailscale_owner_login),
            "editor_connected": int((counts or {"editor_models": 0})["editor_models"]) > 0,
            "backup_monitoring": health_ready,
            "brand_ready": int((counts or {"brand_kits": 0})["brand_kits"]) > 0,
            "library_ready": int((counts or {"assets": 0})["assets"]) > 0,
            "first_delivery": int((counts or {"deliveries": 0})["deliveries"]) > 0,
        },
    }


@router.get("/jobs/manage")
def managed_jobs(state: Literal["active", "archived", "all"] = "active", query: str = Query(default="", max_length=160)) -> list[dict[str, Any]]:
    normalized = " ".join(query.split())
    with connection() as database:
        rows = database.execute(
            """
            SELECT jobs.id, jobs.recipe, jobs.status, jobs.revision, jobs.created_at, jobs.updated_at,
                   jobs.archived_at, jobs.output_aspect, jobs.target_duration_seconds,
                   projects.name AS project_name, projects.brief,
                   COALESCE(usage.requests,0) AS requests, COALESCE(usage.tokens,0) AS total_tokens,
                   EXISTS(SELECT 1 FROM final_exports WHERE final_exports.job_id=jobs.id AND final_exports.status='ready') AS delivered
            FROM jobs JOIN projects ON projects.id=jobs.project_id
            LEFT JOIN LATERAL (SELECT count(*) AS requests, COALESCE(sum(total_tokens),0) AS tokens FROM ai_usage_events WHERE job_id=jobs.id) usage ON true
            WHERE (%s='all' OR (%s='archived')=(jobs.archived_at IS NOT NULL))
              AND (%s='' OR projects.name ILIKE '%%' || %s || '%%' OR projects.brief ILIKE '%%' || %s || '%%')
            ORDER BY jobs.updated_at DESC LIMIT 500
            """,
            (state, state, normalized, normalized, normalized),
        ).fetchall()
    return list(rows)


@router.post("/jobs/{job_id}/archive")
def archive_job(job_id: UUID, x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_editor(actor)
    with connection() as database:
        existing = database.execute("SELECT status FROM jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="job not found")
        if existing["status"] in {"uploading", "ingesting", "analyzing", "planning", "previewing", "revising", "exporting", "rendering"}:
            raise HTTPException(status_code=409, detail="wait for the active job to finish before archiving it")
        row = database.execute("UPDATE jobs SET archived_at=now(), updated_at=now() WHERE id=%s RETURNING id, archived_at", (job_id,)).fetchone()
        _audit(database, actor, "job.archived", "job", str(job_id))
    return row


@router.post("/jobs/{job_id}/restore")
def restore_job(job_id: UUID, x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_editor(actor)
    with connection() as database:
        row = database.execute("UPDATE jobs SET archived_at=NULL, updated_at=now() WHERE id=%s RETURNING id, archived_at", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        _audit(database, actor, "job.restored", "job", str(job_id))
    return row


def _safe_unlink(media_root: Path, relative: str | None) -> int:
    if not relative:
        return 0
    try:
        path = resolve_source(media_root, relative)
        size = path.stat().st_size
        path.unlink()
        return size
    except FileNotFoundError:
        return 0


@router.post("/studio/retention/apply")
def apply_retention(payload: dict[str, str], x_gm_user_login: str | None = Header(default=None)) -> dict[str, Any]:
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    if payload.get("confirmation") != "remove_reproducible_derived_files":
        raise HTTPException(status_code=422, detail="retention confirmation is required")
    media_root = get_settings().media_root
    preview_files = delivery_files = reclaimed = 0
    with connection() as database:
        settings = _settings(database)
        previews = database.execute(
            "SELECT id, preview_path, manifest_path FROM edit_runs WHERE preview_path IS NOT NULL AND completed_at < now() - (%s * interval '1 day') FOR UPDATE",
            (settings["preview_retention_days"],),
        ).fetchall()
        for row in previews:
            for key in ("preview_path", "manifest_path"):
                if row.get(key):
                    reclaimed += _safe_unlink(media_root, str(row[key])); preview_files += 1
            database.execute(
                """
                UPDATE edit_runs SET preview_path=NULL, manifest_path=NULL,
                    manifest=manifest || %s, updated_at=now() WHERE id=%s
                """,
                (Jsonb({"retention": {"derived_files_removed": True, "rebuild_available": True}}), row["id"]),
            )
        for table in ("final_exports", "delivery_variants"):
            rows = database.execute(
                f"SELECT id, video_path, captions_path, cover_path, post_copy_path, package_path, manifest_path FROM {table} WHERE package_path IS NOT NULL AND completed_at < now() - (%s * interval '1 day') FOR UPDATE",
                (settings["delivery_retention_days"],),
            ).fetchall()
            for row in rows:
                for key in ("video_path", "captions_path", "cover_path", "post_copy_path", "package_path", "manifest_path"):
                    if row.get(key):
                        reclaimed += _safe_unlink(media_root, str(row[key])); delivery_files += 1
                database.execute(
                    f"""
                    UPDATE {table} SET status='failed', error='delivery expired by retention; rebuild from the approved edit',
                        video_path=NULL, captions_path=NULL, cover_path=NULL, post_copy_path=NULL,
                        package_path=NULL, manifest_path=NULL, manifest=manifest || %s, updated_at=now()
                    WHERE id=%s
                    """,
                    (Jsonb({"retention": {"derived_files_removed": True, "rebuild_available": True}}), row["id"]),
                )
        run = database.execute("INSERT INTO retention_runs (actor_login, preview_files_removed, delivery_files_removed, bytes_reclaimed) VALUES (%s,%s,%s,%s) RETURNING *", (actor, preview_files, delivery_files, reclaimed)).fetchone()
        _audit(database, actor, "retention.applied", "retention_run", str(run["id"]), {"bytes_reclaimed": reclaimed, "originals_removed": 0})
    return run


@router.get("/studio/audit")
def audit_events(limit: int = Query(default=100, ge=1, le=500), x_gm_user_login: str | None = Header(default=None)) -> list[dict[str, Any]]:
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        return list(database.execute("SELECT * FROM studio_audit_events ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall())
