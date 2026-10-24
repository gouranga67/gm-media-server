#!/usr/bin/env python3
"""Verify the Phase 11 editorial workspace, brand kits, and preset management."""

import json
import os
import sys
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
                key, value = line.split("=", 1); values[key.strip()] = value.strip().strip('"').strip("'")
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
            if response.status != expected: raise RuntimeError(f"{method} {path}: {response.status} {value}")
            return value
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path}: {error.code} {detail}") from error


def main() -> int:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    kit = request("brand-kits", "POST", {
        "name": f"Phase 11 brand {suffix}", "primary_color": "#173F5F", "accent_color": "#FF6B4A",
        "caption_style": "bold", "font_family": "mono",
    }, 201)
    profile = None
    try:
        updated_kit = request(f"brand-kits/{kit['id']}", "PUT", {**{k: kit[k] for k in ("name", "primary_color", "accent_color", "caption_style", "font_family")}, "caption_style": "clean"})
        if updated_kit["caption_style"] != "clean": raise RuntimeError("brand kit update did not round-trip")
        history = request("usage?days=0").get("job_history", [])
        selected = next((job for job in history if job.get("history_kind") == "editing" and job.get("status") in {"delivered", "awaiting_review"}), None)
        if selected is None: raise RuntimeError("complete one real edit before Phase 11 verification")
        review = request(f"jobs/{selected['id']}/review")
        timeline = review.get("editorial_timeline") or []
        if not timeline or not all(item.get("source_name") and item.get("duration", 0) > 0 for item in timeline):
            raise RuntimeError("review does not expose a usable editorial timeline")
        job = review["job"]
        profile = request("creative-profiles", "POST", {
            "name": f"Phase 11 preset {suffix}", "description": "Temporary verification preset",
            "recipe": job["recipe"], "target_duration_seconds": job.get("target_duration_seconds") or 45,
            "edit_style": job.get("edit_style") or "clean", "music_mode": job.get("music_mode") or "none", "target_platform": job.get("target_platform") or "all_social",
            "output_aspect": job["output_aspect"], "reasoning_effort": job["reasoning_effort"],
            "brand_kit_id": kit["id"], "publishing_preset": "instagram_reel", "source_job_id": job["id"],
        }, 201)
        renamed = request(f"creative-profiles/{profile['id']}", "PUT", {"name": profile["name"] + " renamed", "description": profile["description"]})
        if not renamed["name"].endswith("renamed"): raise RuntimeError("profile rename did not round-trip")
        print(json.dumps({
            "status": "passed", "job_id": job["id"], "timeline_clips": len(timeline),
            "brand_kit_round_trip": True, "profile_management": True,
            "publishing_preset": profile["publishing_preset"], "additional_model_tokens": 0,
        }, indent=2))
    finally:
        if profile: request(f"creative-profiles/{profile['id']}", "DELETE", expected=204)
        request(f"brand-kits/{kit['id']}", "DELETE", expected=204)
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as error:
        print(f"Phase 11 verification failed: {error}", file=sys.stderr); raise SystemExit(1)
