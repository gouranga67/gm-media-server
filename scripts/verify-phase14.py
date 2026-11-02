#!/usr/bin/env python3
"""Read-only Phase 14 learning readiness. Never overwrite teaching examples."""

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
    summary = request("learning/summary")
    if summary.get("hosted_model_calls") != 0:
        raise RuntimeError("local learning unexpectedly reported a hosted model call")
    settings = summary.get("settings") or {}
    if int(settings.get("minimum_samples") or 0) < 3:
        raise RuntimeError("learning safeguard allows fewer than three samples")
    if not {"all", "talking_head", "montage"}.issubset(summary.get("scopes", {})):
        raise RuntimeError("learning recipe scopes are incomplete")
    context = request(f"jobs/{job_id}/editor-context")
    learning = context.get("learning_preferences") or {}
    if learning.get("hosted_model_calls") != 0:
        raise RuntimeError("editor learning context is not local-only")

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job_id,
                "read_only": True,
                "feedback_writes": 0,
                "feedback_round_trip": "not run; test deliberate feedback on a disposable edit",
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
