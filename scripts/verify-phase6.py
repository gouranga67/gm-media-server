#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("PHASE6_TIMEOUT_SECONDS", "1800"))


def request(path: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=body,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            decoded = json.load(error)
        except Exception:
            decoded = {"detail": f"HTTP {error.code}"}
        return error.code, decoded


def get_json(path: str) -> dict | list:
    status, payload = request(path)
    if status != 200:
        raise RuntimeError(f"GET {path} failed ({status}): {payload}")
    return payload


def find_chatgpt_preview() -> tuple[str, dict]:
    projects = get_json("projects?limit=100")
    assert isinstance(projects, list)
    fallback: tuple[str, dict] | None = None
    for project in projects:
        jobs = get_json(f"projects/{project['id']}/jobs")
        assert isinstance(jobs, list)
        for job in jobs:
            status, review = request(f"jobs/{job['id']}/review")
            if status != 200:
                continue
            run = review.get("latest_run")
            if not isinstance(run, dict) or run.get("status") != "ready":
                continue
            candidate = (job["id"], run)
            if run.get("provider") == "chatgpt_plan":
                return candidate
            fallback = fallback or candidate
    if fallback is not None:
        return fallback
    raise RuntimeError("no job with a ready preview is available")


def wait_for(path: str, *, status_key: str = "status") -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        payload = get_json(path)
        assert isinstance(payload, dict)
        current = payload.get(status_key)
        if current == "ready":
            return payload
        if current == "failed":
            raise RuntimeError(f"{path} failed: {payload.get('error')}")
        time.sleep(2)
    raise RuntimeError(f"timed out waiting for {path}")


def download_prefix(path: str, length: int = 64) -> bytes:
    with urllib.request.urlopen(f"{BASE_URL}/{path.lstrip('/')}", timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"download {path} returned HTTP {response.status}")
        return response.read(length)


def main() -> int:
    job_id, previous = find_chatgpt_preview()
    revision_status, revision = request(
        f"jobs/{job_id}/revisions",
        method="POST",
        payload={
            "note": (
                "Phase 6 acceptance revision: preserve the strong story and source-only meaning, "
                "but tighten any avoidable pause at the opening."
            ),
            "caption_corrections": [],
        },
    )
    if revision_status != 202:
        raise RuntimeError(f"revision request returned {revision_status}: {revision}")
    expected_version = int(previous["version"]) + 1
    if revision.get("version") != expected_version:
        raise RuntimeError("revision did not create the next immutable version")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        review = get_json(f"jobs/{job_id}/review")
        assert isinstance(review, dict)
        latest = review.get("latest_run") or {}
        if latest.get("version") == expected_version and latest.get("status") == "ready":
            revised = latest
            break
        if latest.get("version") == expected_version and latest.get("status") == "failed":
            raise RuntimeError(f"revised preview failed: {latest.get('error')}")
        time.sleep(2)
    else:
        raise RuntimeError("timed out waiting for revised preview")

    approval_status, final_export = request(
        f"jobs/{job_id}/approval",
        method="POST",
        payload={"version": expected_version, "note": "Phase 6 acceptance approval."},
    )
    if approval_status != 202:
        raise RuntimeError(f"approval returned {approval_status}: {final_export}")
    final_export = wait_for(f"jobs/{job_id}/final")

    video = download_prefix(f"jobs/{job_id}/final/video")
    captions = download_prefix(f"jobs/{job_id}/final/captions")
    cover = download_prefix(f"jobs/{job_id}/final/cover")
    package = download_prefix(f"jobs/{job_id}/final/package")
    manifest = get_json(f"jobs/{job_id}/final/manifest")
    assert isinstance(manifest, dict)
    render = manifest.get("render", {})
    policy = manifest.get("content_policy", {})
    if b"ftyp" not in video or not captions.startswith(b"WEBVTT"):
        raise RuntimeError("final video or captions failed format validation")
    if not cover.startswith(b"\xff\xd8") or not package.startswith(b"PK"):
        raise RuntimeError("cover image or delivery package failed format validation")
    if render.get("width") != 1080 or render.get("height") != 1920:
        raise RuntimeError("final manifest did not confirm 1080 x 1920 output")
    if policy.get("source_derived_only") is not True:
        raise RuntimeError("final manifest did not preserve the source-only policy")

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job_id,
                "revised_run_id": revised["id"],
                "version": expected_version,
                "provider": revised["provider"],
                "final_export_id": final_export["id"],
                "video_encoder": render.get("video_encoder"),
                "full_hd_vertical": True,
                "captions_verified": True,
                "cover_verified": True,
                "package_verified": True,
                "provenance_verified": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
