#!/usr/bin/env python3
"""Verify Phase 13 story intelligence without making a hosted model request."""

import json
import os
import sys
import time
import urllib.error
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
    req = urllib.request.Request(
        f"{BASE}/{path}", data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            value = json.loads(raw) if raw and "json" in response.headers.get("content-type", "") else raw
            if response.status != expected:
                raise RuntimeError(f"{method} {path}: {response.status} {value}")
            return value
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {path}: {error.code} {error.read().decode(errors='replace')}") from error


def wait_for_story_backfill() -> dict:
    deadline = time.monotonic() + 300
    latest = {}
    while time.monotonic() < deadline:
        latest = request("catalog/status")
        ready = int(latest.get("assets_ready") or 0)
        story_ready = int(latest.get("story_assets_ready") or 0)
        if ready > 0 and story_ready >= ready and int(latest.get("story_moments") or 0) > 0:
            return latest
        time.sleep(2)
    raise RuntimeError(f"story-index backfill did not finish: {latest}")


def main() -> int:
    catalog = wait_for_story_backfill()
    library = request("assets/library?limit=100")
    source = next((asset for asset in library if asset.get("mime_type", "").startswith("video/")), None)
    if source is None:
        raise RuntimeError("the library has no video source for story-context verification")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    project = request(
        "projects",
        "POST",
        {
            "name": f"Phase 13 verification — {suffix}",
            "brief": "Build a short source-led story with a clear setup and payoff.",
            "privacy_mode": "local_only",
            "ai_copy_allowed": False,
        },
        201,
    )
    job = request(
        f"projects/{project['id']}/jobs",
        "POST",
        {
            "recipe": "talking_head",
            "target_duration_seconds": 30,
            "edit_style": "clean",
            "music_mode": "none",
            "target_platform": "all_social",
            "must_include": "The strongest supported source point.",
            "audience": "Curious first-time viewers",
            "story_goal": "Understand the main source-backed idea",
            "desired_feeling": "Curious, then satisfied",
            "ending_instruction": "Finish on the clearest supported conclusion",
            "reasoning_effort": "low",
            "output_aspect": "vertical",
        },
        201,
    )
    request(f"jobs/{job['id']}/assets", "POST", {"asset_ids": [source["id"]]})
    context = request(f"jobs/{job['id']}/editor-context")
    spine = context.get("story_spine") or {}
    if spine.get("audience") != "Curious first-time viewers":
        raise RuntimeError("story audience did not round-trip")
    if spine.get("goal") != "Understand the main source-backed idea":
        raise RuntimeError("story goal did not round-trip")
    indexed = context.get("assets", [{}])[0].get("story_index") or {}
    moments = indexed.get("moments") or []
    if indexed.get("status") != "ready" or not moments:
        raise RuntimeError("the attached source has no ready story moments")
    if not all(
        isinstance(moment.get("start_seconds"), (int, float))
        and isinstance(moment.get("end_seconds"), (int, float))
        and moment.get("evidence")
        and moment.get("suggested_roles")
        for moment in moments
    ):
        raise RuntimeError("story moments are missing source range, evidence, or narrative roles")
    request(f"jobs/{job['id']}/archive", "POST", {})
    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job["id"],
                "story_version": indexed.get("version"),
                "story_assets_ready": catalog["story_assets_ready"],
                "story_moments_cached": catalog["story_moments"],
                "retrieved_moments": len(moments),
                "story_spine_round_trip": True,
                "source_ranges_verified": True,
                "additional_model_tokens": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 13 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
