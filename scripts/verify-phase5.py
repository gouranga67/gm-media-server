#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("PHASE5_TIMEOUT_SECONDS", "900"))


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


def get_json(path: str) -> dict:
    status, payload = request(path)
    if status != 200:
        raise RuntimeError(f"GET {path} failed ({status}): {payload}")
    return payload


def find_ready_job() -> tuple[str, dict]:
    projects = get_json("projects?limit=100")
    for project in projects:
        jobs = get_json(f"projects/{project['id']}/jobs")
        for job in jobs:
            context = get_json(f"jobs/{job['id']}/editor-context")
            candidates = [
                asset
                for asset in context.get("assets", [])
                if asset.get("has_video") and asset.get("has_audio")
            ]
            if context.get("ready_for_editing") and candidates:
                return job["id"], context
    raise RuntimeError("no job with fully analyzed video and audio is available")


def plan_for(context: dict, invented_asset_id: str | None = None) -> dict:
    assets = [
        asset
        for asset in context["assets"]
        if asset.get("has_video") and asset.get("has_audio")
    ]
    requested = float(context["job"].get("target_duration_seconds") or 10)
    total_available = sum(float(asset.get("duration_seconds") or 0) for asset in assets)
    desired = min(requested, total_available, 60.0)
    style = context["job"].get("edit_style") or "clean"
    clips: list[dict] = []
    remaining = desired
    for asset in assets:
        duration = float(asset.get("duration_seconds") or 0)
        take = min(duration, remaining)
        if take < 0.25:
            continue
        if not clips and style == "energetic" and take >= 4:
            split = round(take / 2, 3)
            ranges = [(0.0, split), (split, round(take, 3))]
        else:
            ranges = [(0.0, round(take, 3))]
        for source_in, source_out in ranges:
            clips.append(
                {
                    "asset_id": asset["asset_id"],
                    "source_in": source_in,
                    "source_out": source_out,
                    "crop": "center_fill",
                    "transition": "cut",
                    "visual_preset": "standard",
                }
            )
        remaining -= take
        if remaining <= 0.01:
            break
    if not clips:
        raise RuntimeError("no usable source range is available")
    if invented_asset_id is not None:
        clips[0]["asset_id"] = invented_asset_id
    if style == "energetic" and desired >= 8:
        clips[-1]["visual_preset"] = "punch_in"
    if style == "energetic" and desired >= 20 and len(clips) > 1:
        clips[1]["transition"] = "dip_to_black"
    music_library = context.get("music_library", [])
    music_mode = context["job"].get("music_mode") or "none"
    selected_music = music_library[0]["track_id"] if music_mode != "none" and music_library else None
    return {
        "schema_version": "1.1",
        "recipe": "talking_head",
        "clips": clips,
        "caption_style": "clean_blue_v1",
        "audio_preset": "spoken_voice_v1",
        "end_card": "none",
        "editorial_summary": "Phase 5 deterministic source-only rendering check.",
        "post_copy": "",
        "music_track_id": selected_music,
        "music_mix": music_mode if selected_music else "none",
    }


def main() -> int:
    job_id, context = find_ready_job()
    asset = next(
        item for item in context["assets"] if item.get("has_video") and item.get("has_audio")
    )
    duration = float(asset.get("duration_seconds") or 0)
    if duration < 0.25:
        raise RuntimeError("the selected source is too short for a preview")

    invented = plan_for(context, str(uuid4()))
    invalid_status, invalid_payload = request(
        f"jobs/{job_id}/edit-plans", method="POST", payload=invented
    )
    if invalid_status != 422:
        raise RuntimeError(
            f"invented asset safety check returned {invalid_status}, expected 422: {invalid_payload}"
        )

    valid_status, run = request(
        f"jobs/{job_id}/edit-plans",
        method="POST",
        payload=plan_for(context),
    )
    if valid_status != 202:
        raise RuntimeError(f"valid edit plan returned {valid_status}: {run}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = get_json(f"jobs/{job_id}/preview")
        if current["status"] == "ready":
            break
        if current["status"] == "failed":
            raise RuntimeError(f"preview failed: {current.get('error')}")
        time.sleep(2)
    else:
        raise RuntimeError("timed out waiting for the Phase 5 preview")

    with urllib.request.urlopen(
        f"{BASE_URL}/jobs/{job_id}/preview/file", timeout=30
    ) as response:
        prefix = response.read(32)
        if response.status != 200 or b"ftyp" not in prefix:
            raise RuntimeError("preview download is not a valid MP4 response")

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": job_id,
                "run_id": current["id"],
                "version": current["version"],
                "provider": current["provider"],
                "model": current["model"],
                "video_encoder": current.get("manifest", {}).get("render", {}).get(
                    "video_encoder"
                ),
                "invented_asset_rejected": True,
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
        print(f"Phase 5 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
