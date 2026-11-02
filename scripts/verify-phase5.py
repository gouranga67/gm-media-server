#!/usr/bin/env python3
import json
import os
import runpy
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4
from pathlib import Path


BASE_URL = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["BASE"]
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
                and float(asset.get("duration_seconds") or 0) >= 4
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


def create_fixture(context: dict) -> tuple[str, dict]:
    asset = next((item for item in context["assets"] if item.get("has_video") and item.get("has_audio")
                  and float(item.get("duration_seconds") or 0) >= 4), None)
    if asset is None:
        raise RuntimeError("a source of at least four seconds is needed for the isolated renderer check")
    def create(path, payload, expected):
        status, result = request(path, method="POST", payload=payload)
        if status != expected:
            raise RuntimeError(f"verification fixture {path} returned {status}: {result}")
        return result
    project = create("projects", {"name":"Phase 5 verification — isolated renderer",
        "brief":"Technical source-only render check; no hosted editing request.",
        "privacy_mode":"local_only","ai_copy_allowed":False}, 201)
    job = create(f"projects/{project['id']}/jobs", {"recipe":"talking_head","assembly_mode":"talking_head",
        "pacing_mode":"manual","edit_style":"clean","music_mode":"none","effect_level":"off",
        "target_duration_seconds":15,"max_duration_seconds":15}, 201)
    job_id = job["id"]
    try:
        create(f"jobs/{job_id}/assets", {"asset_ids":[asset["asset_id"]]}, 200)
        fixture_context = get_json(f"jobs/{job_id}/editor-context")
        if not fixture_context.get("ready_for_editing"):
            raise RuntimeError("the isolated renderer fixture is not ready")
        return job_id, fixture_context
    except Exception:
        request(f"jobs/{job_id}/archive", method="POST", payload={})
        raise


def check_fixture(job_id: str, context: dict) -> dict:
    asset = next(
        item for item in context["assets"] if item.get("has_video") and item.get("has_audio")
    )
    duration = float(asset.get("duration_seconds") or 0)
    if duration < 0.25:
        raise RuntimeError("the selected source is too short for a preview")

    # Keep the live check short, while the stored job still has a valid 15s
    # preference. A complete technical fixture need not fill that preference.
    context = {**context,"job":{**context["job"],"target_duration_seconds":8}}
    document = plan_for(context)
    first = document["clips"][0]
    split = round((first["source_in"]+first["source_out"])/2,3)
    document["clips"] = [{**first,"source_out":split}, {**first,"source_in":split,"transition":"cross_dissolve"}]
    duration = split-first["source_in"]
    document.update(schema_version="1.5",finishing={
        "motions":[{"clip_index":0,"points":[{"time":0,"zoom":1,"x":.5,"y":.5},
            {"time":duration,"zoom":1.12,"x":.5,"y":.5}]}],
        "caption_regions":[{"start":.5,"end":min(1.5,duration),"position":"upper"}]})
    invented = {**document,"clips":[{**document["clips"][0],"asset_id":str(uuid4())},*document["clips"][1:]]}
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
        payload=document,
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

    review = get_json(f"jobs/{job_id}/review")
    if int(review.get("usage",{}).get("requests",-1)) != 0:
        raise RuntimeError("the isolated deterministic renderer unexpectedly recorded a model request")
    events = current.get("manifest",{}).get("finishing",{}).get("treatment_timeline",{}).get("events",[])
    if not {"framing","transition","captions"}.issubset({event.get("kind") for event in events}):
        raise RuntimeError("the rendered treatment report is missing camera, dissolve or caption evidence")
    return {
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
                "preview_download_verified": True,
                "download_check": "MP4 response; physical phone playback remains manual",
                "isolated_verification_job": True,
                "treatment_events": len(events),
                "additional_model_tokens": 0,
            }


def main() -> int:
    _, source_context = find_ready_job()
    job_id, context = create_fixture(source_context)
    fixture_archived = False
    try:
        report = check_fixture(job_id,context)
    finally:
        # Do not hide an in-progress render if its request/polling was interrupted.
        status, current = request(f"jobs/{job_id}/preview")
        if status == 404 or current.get("status") in {"ready","failed"}:
            archived, _ = request(f"jobs/{job_id}/archive",method="POST",payload={})
            if archived != 200:
                raise RuntimeError("the renderer check finished but its verification job could not be archived")
            fixture_archived = True
    if not fixture_archived:
        raise RuntimeError("the render passed but its fixture state could not be confirmed for cleanup")
    print(json.dumps({**report,"fixture_archived":True},indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 5 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
