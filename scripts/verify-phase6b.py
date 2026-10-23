#!/usr/bin/env python3
"""Verify a real, approved montage after it has been created from the phone."""

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("PHASE6B_TIMEOUT_SECONDS", "1800"))


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


def get_json(path: str) -> dict | list:
    status, payload = request(path)
    if status != 200:
        raise RuntimeError(f"GET {path} failed ({status}): {payload}")
    return payload


def download_prefix(path: str, length: int = 64) -> bytes:
    with urllib.request.urlopen(f"{BASE_URL}/{path.lstrip('/')}", timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"download {path} returned HTTP {response.status}")
        return response.read(length)


def refresh_legacy_delivery(job: dict, run: dict) -> dict:
    status, export = request(
        f"jobs/{job['id']}/approval",
        method="POST",
        payload={
            "version": run["version"],
            "note": "Refresh approved montage with current caption renderer.",
        },
    )
    if status != 202 or not isinstance(export, dict):
        raise RuntimeError(f"legacy montage refresh returned {status}: {export}")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = get_json(f"jobs/{job['id']}/final")
        assert isinstance(current, dict)
        if current.get("status") == "ready":
            return current
        if current.get("status") == "failed":
            raise RuntimeError(f"refreshed montage delivery failed: {current.get('error')}")
        time.sleep(2)
    raise RuntimeError("timed out refreshing the legacy montage delivery")


def find_delivered_montage() -> tuple[dict, dict, dict]:
    projects = get_json("projects?limit=100")
    assert isinstance(projects, list)
    legacy_jobs: list[str] = []
    for project in projects:
        jobs = get_json(f"projects/{project['id']}/jobs")
        assert isinstance(jobs, list)
        for job in jobs:
            if job.get("recipe") != "montage":
                continue
            review = get_json(f"jobs/{job['id']}/review")
            assert isinstance(review, dict)
            run = review.get("latest_run") or {}
            final_export = review.get("final_export") or {}
            if (
                run.get("status") == "ready"
                and final_export.get("status") == "ready"
                and final_export.get("version") == run.get("version")
            ):
                manifest = get_json(f"jobs/{job['id']}/final/manifest")
                assert isinstance(manifest, dict)
                caption_metadata = manifest.get("captions") or {}
                if caption_metadata.get("style") == "clean_blue_v1":
                    return job, review, manifest
                refresh_legacy_delivery(job, run)
                manifest = get_json(f"jobs/{job['id']}/final/manifest")
                assert isinstance(manifest, dict)
                caption_metadata = manifest.get("captions") or {}
                if caption_metadata.get("style") == "clean_blue_v1":
                    refreshed_review = get_json(f"jobs/{job['id']}/review")
                    assert isinstance(refreshed_review, dict)
                    return job, refreshed_review, manifest
                legacy_jobs.append(str(job["id"]))
    if legacy_jobs:
        raise RuntimeError(
            "delivered montage(s) predate caption provenance; approve a montage "
            "rendered by the current build, then rerun this check (legacy jobs: "
            + ", ".join(legacy_jobs[:5])
            + ")"
        )
    raise RuntimeError("no approved montage with a ready final delivery was found")


def main() -> int:
    models = get_json("editor/models")
    if not isinstance(models, list) or not models:
        raise RuntimeError("the connected ChatGPT account returned no selectable models")
    if not all(item.get("slug") and item.get("display_name") for item in models):
        raise RuntimeError("the editor model catalogue is incomplete")

    dashboard = get_json("usage?days=0")
    assert isinstance(dashboard, dict)
    history = dashboard.get("job_history")
    if not isinstance(history, list) or not history:
        raise RuntimeError("the all-time usage dashboard returned no job history")
    required_job_fields = {"id", "project_name", "recipe", "status", "requests", "total_tokens"}
    if any(not required_job_fields.issubset(item) for item in history):
        raise RuntimeError("the usage dashboard job history is incomplete")
    job, review, manifest = find_delivered_montage()
    run = review["latest_run"]
    usage = review.get("usage") or {}
    if run.get("provider") != "chatgpt_plan":
        raise RuntimeError("the montage was not planned through the connected ChatGPT account")
    if int(usage.get("requests") or 0) < 1:
        raise RuntimeError("the montage has no recorded hosted editor request")
    token_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    if any(int(usage.get(field, -1)) < 0 for field in token_fields):
        raise RuntimeError("the montage usage ledger contains an invalid token count")

    video = download_prefix(f"jobs/{job['id']}/final/video")
    captions = download_prefix(f"jobs/{job['id']}/final/captions")
    package = download_prefix(f"jobs/{job['id']}/final/package")
    if b"ftyp" not in video or not captions.startswith(b"WEBVTT") or not package.startswith(b"PK"):
        raise RuntimeError("a final montage delivery artifact failed format validation")
    if manifest.get("recipe") != "montage":
        raise RuntimeError("the final manifest is not a montage")
    expected = (1920, 1080) if job.get("output_aspect") == "landscape" else (1080, 1920)
    render = manifest.get("render") or {}
    if (render.get("width"), render.get("height")) != expected:
        raise RuntimeError("the final montage dimensions do not match the selected output shape")
    caption_metadata = manifest.get("captions") or {}
    if caption_metadata.get("style") != "clean_blue_v1":
        raise RuntimeError("the final montage does not declare its caption style")

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job["id"],
                "run_id": run["id"],
                "version": run["version"],
                "model": run.get("model"),
                "reasoning_effort": run.get("reasoning_effort"),
                "total_tokens": usage.get("total_tokens"),
                "selectable_models": len(models),
                "dashboard_requests_all_time": dashboard.get("requests"),
                "dashboard_jobs_all_time": dashboard.get("jobs"),
                "caption_events": caption_metadata.get("events"),
                "output_aspect": job.get("output_aspect"),
                "video_encoder": render.get("video_encoder"),
                "phone_download_verified": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6B verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
