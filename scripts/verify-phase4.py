#!/usr/bin/env python3
"""Validate the local analysis manifest for a real, finalized media asset."""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


BASE_URL = os.environ.get(
    "GM_MEDIA_URL", "http://127.0.0.1:3000/api/media"
).rstrip("/")


def json_request(path: str) -> Any:
    request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}", headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def choose_asset() -> dict[str, Any]:
    projects = json_request("projects?limit=100")
    candidates: list[dict[str, Any]] = []
    for project in projects:
        assets = json_request(f"projects/{project['id']}/assets")
        candidates.extend(
            asset
            for asset in assets
            if asset["status"] == "ready"
            and asset.get("byte_size", 0) >= 100_000
            and str(asset.get("mime_type", "")).startswith(("video/", "audio/"))
        )
    if not candidates:
        raise RuntimeError("no finalized real media asset is available; upload a phone clip first")
    return max(candidates, key=lambda asset: asset["created_at"])


def get_analysis(asset_id: str) -> dict[str, Any] | None:
    try:
        return json_request(f"assets/{asset_id}/analysis")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            try:
                payload = json.loads(error.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            detail = payload.get("detail")
            if detail == "asset analysis has not been queued":
                return None
            if detail == "Not Found":
                raise RuntimeError(
                    "Phase 4 API route is not deployed; restart the service with the updated installer"
                ) from error
        raise


def validate(analysis: dict[str, Any]) -> dict[str, Any]:
    manifest = analysis.get("manifest", {})
    probe = manifest.get("probe", {})
    streams = probe.get("streams", [])
    derived = manifest.get("derived", {})
    policy = manifest.get("content_policy", {})

    if manifest.get("schema_version") != "1.0":
        raise RuntimeError("analysis manifest schema version is missing or unexpected")
    if policy != {"source_derived_only": True, "synthetic_media": False}:
        raise RuntimeError("source-only content policy is missing from the analysis manifest")
    if not streams:
        raise RuntimeError("ffprobe did not record any audio or video streams")
    if not manifest.get("manifest_path"):
        raise RuntimeError("manifest path is missing")

    stream_types = {stream.get("type") for stream in streams}
    required = {"proxy"}
    if "video" in stream_types:
        required.update({"thumbnail", "contact_sheet", "scene_boundaries_seconds", "visual_quality"})
    if "audio" in stream_types:
        required.update({"transcript", "captions", "loudness"})
    missing = sorted(key for key in required if key not in derived)
    if missing:
        raise RuntimeError(f"analysis manifest is missing derived outputs: {', '.join(missing)}")

    return {
        "status": "passed",
        "asset_id": analysis["asset_id"],
        "attempts": analysis["attempts"],
        "stream_types": sorted(stream_types),
        "duration_seconds": probe.get("format", {}).get("duration_seconds"),
        "derived_outputs": sorted(derived),
        "manifest_path": manifest["manifest_path"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-id", help="specific ready asset to verify")
    parser.add_argument("--timeout", type=int, default=7200, help="seconds to wait for analysis")
    arguments = parser.parse_args()

    asset = (
        json_request(f"assets/{arguments.asset_id}")
        if arguments.asset_id
        else choose_asset()
    )
    if asset["status"] != "ready":
        raise RuntimeError(f"asset is {asset['status']}, not ready")

    deadline = time.monotonic() + arguments.timeout
    last_status = "not queued"
    while time.monotonic() < deadline:
        analysis = get_analysis(asset["id"])
        if analysis is None:
            last_status = "not queued"
        else:
            last_status = analysis["status"]
            if last_status == "ready":
                print(json.dumps(validate(analysis), indent=2))
                return
            if last_status == "failed":
                raise RuntimeError(f"analysis failed: {analysis.get('error', 'unknown error')}")
        time.sleep(5)

    raise RuntimeError(f"analysis remained {last_status} after {arguments.timeout} seconds")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, urllib.error.URLError) as error:
        raise SystemExit(str(error)) from error
