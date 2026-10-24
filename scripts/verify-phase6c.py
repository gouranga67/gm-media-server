#!/usr/bin/env python3
"""Verify reusable server media can be attached without copying its original."""

import json
import os
import sys
import urllib.error
import urllib.request
from uuid import UUID


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")
PROJECT_ID = UUID("6c000000-0000-4000-8000-000000000001")
JOB_ID = UUID("6c000000-0000-4000-8000-000000000002")


def request(
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict | list]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=body,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            decoded = json.load(error)
        except Exception:
            decoded = {"detail": f"HTTP {error.code}"}
        return error.code, decoded


def require(path: str, expected: int, *, method: str = "GET", payload: dict | None = None):
    status, response = request(path, method=method, payload=payload)
    if status != expected:
        raise RuntimeError(f"{method} {path} returned {status}: {response}")
    return response


def main() -> int:
    library = require("assets/library?limit=500", 200)
    if not isinstance(library, list) or not library:
        raise RuntimeError("the server library contains no analyzed media")
    asset = next((item for item in library if item.get("mime_type", "").startswith(("video/", "image/"))), library[0])
    project_id = str(PROJECT_ID)
    job_id = str(JOB_ID)
    project = require(
        "projects",
        201,
        method="POST",
        payload={
            "id": project_id,
            "name": "Phase 6C library verification",
            "brief": "Verify an existing original can be reused without copying media bytes.",
            "privacy_mode": "local_only",
            "ai_copy_allowed": False,
        },
    )
    if not isinstance(project, dict) or project.get("id") != project_id:
        raise RuntimeError("verification project was not created with its stable ID")
    job = require(
        f"projects/{project_id}/jobs",
        201,
        method="POST",
        payload={"id": job_id, "recipe": "talking_head", "target_duration_seconds": 20},
    )
    if not isinstance(job, dict) or job.get("id") != job_id:
        raise RuntimeError("verification job was not created with its stable ID")

    already_attached = require(f"jobs/{job_id}/assets", 200)
    if not isinstance(already_attached, list):
        raise RuntimeError("the verification job asset response is invalid")
    source_lock_verified = job.get("status") != "draft"
    idempotency_rechecked = not source_lock_verified
    new_reference_created = False
    if source_lock_verified:
        library_by_id = {item.get("id"): item for item in library}
        reusable = next(
            (
                library_by_id.get(item.get("id"))
                for item in already_attached
                if item.get("id") in library_by_id
            ),
            None,
        )
        if not isinstance(reusable, dict):
            raise RuntimeError("the completed verification job has no active library reference")
        asset = reusable
        late_status, _ = request(
            f"jobs/{job_id}/assets",
            method="POST",
            payload={"asset_ids": [asset["id"]]},
        )
        if late_status != 409:
            raise RuntimeError("a non-draft job allowed its source inventory to change")
    else:
        expected_first_count = int(asset["id"] not in {item.get("id") for item in already_attached})
        first = require(
            f"jobs/{job_id}/assets",
            200,
            method="POST",
            payload={"asset_ids": [asset["id"]]},
        )
        second = require(
            f"jobs/{job_id}/assets",
            200,
            method="POST",
            payload={"asset_ids": [asset["id"]]},
        )
        if not isinstance(first, dict) or first.get("attached_count") != expected_first_count:
            raise RuntimeError("the first library attachment did not have the expected idempotent result")
        if not isinstance(second, dict) or second.get("attached_count") != 0:
            raise RuntimeError("repeating the library attachment was not idempotent")
        new_reference_created = bool(expected_first_count)

    required = {"id", "project_id", "project_name", "source_name", "mime_type", "byte_size", "sha256"}
    if not required.issubset(asset):
        raise RuntimeError("the server library item is missing provenance fields")
    original = require(f"assets/{asset['id']}", 200)
    if not isinstance(original, dict):
        raise RuntimeError("the selected original response is invalid")

    attached = require(f"jobs/{job_id}/assets", 200)
    if not isinstance(attached, list) or [item.get("id") for item in attached].count(asset["id"]) != 1:
        raise RuntimeError("the job does not contain exactly one reference to the reused asset")
    reused = next(item for item in attached if item.get("id") == asset["id"])
    if reused.get("storage_key") != original.get("storage_key") or reused.get("sha256") != original.get("sha256"):
        raise RuntimeError("the reused job asset does not reference the immutable original")

    thumbnail_verified = False
    if asset.get("thumbnail_available"):
        with urllib.request.urlopen(f"{BASE_URL}/assets/{asset['id']}/thumbnail", timeout=60) as response:
            thumbnail_verified = response.status == 200 and response.read(2) == b"\xff\xd8"
        if not thumbnail_verified:
            raise RuntimeError("the library thumbnail is not a valid JPEG")

    print(
        json.dumps(
            {
                "status": "passed",
                "asset_id": asset["id"],
                "origin_project_id": asset["project_id"],
                "attached_job_id": job_id,
                "same_storage_key": True,
                "same_sha256": True,
                "idempotency_rechecked": idempotency_rechecked,
                "source_lock_verified": source_lock_verified,
                "new_reference_created": new_reference_created,
                "thumbnail_verified": thumbnail_verified,
                "library_items": len(library),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6C verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
