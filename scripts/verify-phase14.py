#!/usr/bin/env python3
"""Verify the local Phase 14 learning loop without making a model request."""

import json
import os
import sys
import urllib.error
import urllib.request
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


def main() -> int:
    history = request("usage?days=0").get("job_history") or []
    selected = None
    review = None
    for job in history:
        if job.get("history_kind") != "editing":
            continue
        candidate = request(f"jobs/{job['id']}/review")
        run = candidate.get("latest_run") or {}
        if run.get("status") == "ready":
            selected = job
            review = candidate
            break
    if selected is None or review is None:
        raise RuntimeError("no finished edit is available for learning-loop verification")

    job_id = selected["id"]
    run = review["latest_run"]
    previous = review.get("latest_feedback")
    temporary = {
        "edit_run_id": run["id"],
        "rating": 4,
        "tags": ["strong_hook", "clear_story"],
        "note": "Phase 14 reversible learning verification.",
        "would_use_again": True,
    }
    saved = request(f"jobs/{job_id}/feedback", "POST", temporary)
    try:
        if saved.get("rating") != 4 or saved.get("tags") != temporary["tags"]:
            raise RuntimeError("edit feedback did not round-trip")
        summary = request("learning/summary")
        if int(summary.get("feedback_count") or 0) < 1:
            raise RuntimeError("learning dashboard did not include the saved feedback")
        if summary.get("hosted_model_calls") != 0:
            raise RuntimeError("local learning unexpectedly reported a hosted model call")
        settings = summary.get("settings") or {}
        if int(settings.get("minimum_samples") or 0) < 3:
            raise RuntimeError("learning safeguard allows fewer than three samples")
        context = request(f"jobs/{job_id}/editor-context")
        learning = context.get("learning_preferences") or {}
        if learning.get("hosted_model_calls") != 0:
            raise RuntimeError("editor learning context is not local-only")
    finally:
        if previous:
            request(
                f"jobs/{job_id}/feedback",
                "POST",
                {
                    "edit_run_id": previous["edit_run_id"],
                    "rating": previous["rating"],
                    "tags": previous["tags"],
                    "note": previous["note"],
                    "would_use_again": previous["would_use_again"],
                },
            )
        else:
            request(f"jobs/{job_id}/feedback/{run['id']}", "DELETE", expected=204)

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job_id,
                "feedback_round_trip": True,
                "feedback_restored": True,
                "minimum_samples": settings["minimum_samples"],
                "recipe_scopes": sorted(summary.get("scopes", {}).keys()),
                "future_context_verified": True,
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
        print(f"Phase 14 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
