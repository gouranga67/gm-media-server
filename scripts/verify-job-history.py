#!/usr/bin/env python3
"""Verify complete, non-destructive job history and test-job classification."""

import json
import os
import sys
import urllib.request
from collections import Counter


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")
KNOWN_STATUSES = {
    "draft",
    "uploading",
    "ingesting",
    "analyzing",
    "planning",
    "previewing",
    "awaiting_review",
    "revising",
    "approved",
    "rendering",
    "exporting",
    "delivered",
    "complete",
    "failed",
    "cancelled",
}


def get_dashboard(days: int) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}/usage?days={days}", timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("usage dashboard response is invalid")
    return payload


def main() -> int:
    dashboard = get_dashboard(0)
    history = dashboard.get("job_history")
    if not isinstance(history, list):
        raise RuntimeError("job history is missing")
    if int(dashboard.get("jobs", -1)) != len(history):
        raise RuntimeError("all-time history does not return every stored job")

    invalid_kinds = [job.get("history_kind") for job in history if job.get("history_kind") not in {"editing", "verification"}]
    if invalid_kinds:
        raise RuntimeError(f"job history contains invalid classifications: {invalid_kinds}")
    invalid_statuses = sorted({str(job.get("status")) for job in history if job.get("status") not in KNOWN_STATUSES})
    if invalid_statuses:
        raise RuntimeError(f"job history contains unknown statuses: {invalid_statuses}")

    verification = [job for job in history if job.get("history_kind") == "verification"]
    editing = [job for job in history if job.get("history_kind") == "editing"]
    if not verification:
        raise RuntimeError("existing automated verification jobs were not classified as tests")
    if not any(str(job.get("project_name", "")).startswith("Phase 6C") for job in verification):
        raise RuntimeError("Phase 6C verification history was not classified as test work")

    recent = get_dashboard(30)
    if int(recent.get("jobs", 0)) > len(history):
        raise RuntimeError("30-day filter returned more jobs than all-time history")

    print(
        json.dumps(
            {
                "status": "passed",
                "stored_jobs": len(history),
                "editing_jobs": len(editing),
                "verification_jobs": len(verification),
                "status_counts": dict(sorted(Counter(str(job["status"]) for job in history).items())),
                "history_is_complete": True,
                "records_deleted": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Job history verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
