#!/usr/bin/env python3
"""Verify Phase 12 product controls without spending model tokens or deleting originals."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def base_url() -> str:
    if os.environ.get("GM_MEDIA_URL"):
        return os.environ["GM_MEDIA_URL"].rstrip("/")
    values = {}
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get("TAILSCALE_AUTH_REQUIRED", "").lower() == "true" and values.get("APP_ORIGIN"):
        return values["APP_ORIGIN"].rstrip("/") + "/api/media"
    return "http://127.0.0.1:3000/api/media"


BASE = base_url()


def request(path: str, method: str = "GET", payload=None, expected: int = 200):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/{path}", data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            value = json.loads(raw) if raw and "json" in response.headers.get("content-type", "") else raw
            if response.status != expected:
                raise RuntimeError(f"{method} {path}: {response.status} {value}")
            return value
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {path}: {error.code} {error.read().decode(errors='replace')}") from error


def settings_payload(value: dict, **overrides) -> dict:
    result = {
        key: value[key]
        for key in (
            "studio_name", "onboarding_completed", "daily_ai_token_limit", "monthly_ai_token_limit",
            "max_active_jobs", "preview_retention_days", "delivery_retention_days",
        )
    }
    result.update(overrides)
    return result


def main() -> int:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    login = f"phase12-{suffix}@example.invalid"
    original_settings = request("studio/settings")
    job_id = None
    member_created = False
    job_archived = False
    try:
        me = request("members/me")
        if me.get("role") != "owner":
            raise RuntimeError("the configured Tailscale owner was not bootstrapped")
        created = request("members", "POST", {"login": login, "display_name": "Phase 12 verifier", "role": "viewer"}, 201)
        member_created = True
        if created["role"] != "viewer":
            raise RuntimeError("viewer role did not round-trip")
        updated = request(f"members/{urllib.parse.quote(login, safe='')}", "PUT", {"display_name": "Phase 12 verifier", "role": "editor", "active": False})
        if updated["role"] != "editor" or updated["active"]:
            raise RuntimeError("member role and pause state did not round-trip")
        request(f"members/{urllib.parse.quote(login, safe='')}", "PUT", {"display_name": "Phase 12 verifier", "role": "editor", "active": True})

        limited = request("studio/settings", "PUT", settings_payload(
            original_settings,
            daily_ai_token_limit=max(original_settings["budget"]["today_tokens"] + 1000, 1000),
            monthly_ai_token_limit=max(original_settings["budget"]["month_tokens"] + 1000, 1000),
            preview_retention_days=3650,
            delivery_retention_days=3650,
        ))
        if not limited["budget"]["allowed"]:
            raise RuntimeError("a budget above measured usage was incorrectly blocked")

        overview = request("studio/overview")
        required = {"counts", "budget", "storage", "retention", "readiness", "settings"}
        if not required.issubset(overview):
            raise RuntimeError("studio overview is incomplete")
        jobs = request("jobs/manage?state=active&query=")
        active_statuses = {
            "uploading", "ingesting", "analyzing", "planning",
            "previewing", "revising", "exporting", "rendering",
        }
        selected = next((job for job in jobs if job.get("status") not in active_statuses), None)
        if selected is None:
            raise RuntimeError("no idle job is available for archive/restore verification")
        job_id = selected["id"]
        archived = request(f"jobs/{job_id}/archive", "POST", {})
        job_archived = archived.get("archived_at") is not None
        if not job_archived:
            raise RuntimeError("job archive did not persist")
        restored = request(f"jobs/{job_id}/restore", "POST", {})
        job_archived = False
        if restored.get("archived_at") is not None:
            raise RuntimeError("job restore did not persist")

        cleanup = request("studio/retention/apply", "POST", {"confirmation": "remove_reproducible_derived_files"})
        if cleanup.get("originals_removed") != 0:
            raise RuntimeError("retention reported removing an original")
        audit = request("studio/audit?limit=100")
        if not any(event.get("action") == "retention.applied" for event in audit):
            raise RuntimeError("retention audit event is missing")
        print(json.dumps({
            "status": "passed",
            "owner_bootstrapped": True,
            "member_roles_round_trip": True,
            "job_archive_round_trip": True,
            "onboarding_readiness": overview["readiness"],
            "budget_controls": True,
            "retention_audited": True,
            "originals_removed": cleanup["originals_removed"],
            "additional_model_tokens": 0,
        }, indent=2))
    finally:
        if job_archived and job_id:
            request(f"jobs/{job_id}/restore", "POST", {})
        if member_created:
            request(f"members/{urllib.parse.quote(login, safe='')}", "DELETE", expected=204)
        request("studio/settings", "PUT", settings_payload(original_settings))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 12 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
