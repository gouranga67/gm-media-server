#!/usr/bin/env python3
"""Verify local canonical-aware semantic visual indexing and search."""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")


def request(path: str) -> tuple[int, dict | list | bytes]:
    http_request = urllib.request.Request(f"{BASE_URL}/{path.lstrip('/')}", method="GET")
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            if response.headers.get_content_type() == "application/json":
                return response.status, json.load(response)
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        try:
            decoded = json.load(error)
        except Exception:
            decoded = {"detail": f"HTTP {error.code}"}
        return error.code, decoded


def require(path: str, expected: int):
    status, response = request(path)
    if status != expected:
        raise RuntimeError(f"GET {path} returned {status}: {response}")
    return response


def main() -> int:
    deadline = time.monotonic() + 1200
    status = None
    while time.monotonic() < deadline:
        status = require("catalog/visual/status", 200)
        if not isinstance(status, dict):
            raise RuntimeError("visual index status response is invalid")
        if int(status.get("assets_pending", 0)) == 0:
            break
        time.sleep(5)
    if not isinstance(status, dict) or int(status.get("assets_pending", -1)) != 0:
        raise RuntimeError("visual index backfill did not finish within twenty minutes")
    if int(status.get("assets_failed", 0)) != 0:
        raise RuntimeError(f"visual index contains failed assets: {status['assets_failed']}")
    if int(status.get("assets_ready", 0)) == 0 or int(status.get("frames_total", 0)) == 0:
        raise RuntimeError("visual index contains no searchable source frames")
    if status.get("local_only") is not True:
        raise RuntimeError("visual index does not declare local-only inference")

    parameters = urllib.parse.urlencode({"query": "fighter jet", "media_kind": "video", "limit": 25})
    search = require(f"catalog/search?{parameters}", 200)
    if not isinstance(search, dict) or not isinstance(search.get("results"), list):
        raise RuntimeError("visual search response is invalid")
    match = next(
        (
            item
            for item in search["results"]
            if "visual" in item.get("evidence_kinds", [])
            and item.get("visual_frame_id") is not None
            and "plane" in str(item.get("source_name", "")).lower()
        ),
        None,
    )
    if not isinstance(match, dict):
        raise RuntimeError("fighter jet did not return the known plane source as a visual match")
    if match.get("text") and match.get("segment_kind") == "visual":
        raise RuntimeError("visual-only result invented a textual scene description")
    if float(match.get("end_seconds", 0)) < float(match.get("start_seconds", 0)):
        raise RuntimeError("visual result contains an invalid source time range")
    frame = require(f"catalog/visual/frames/{match['visual_frame_id']}", 200)
    if not isinstance(frame, bytes) or not frame.startswith(b"\xff\xd8"):
        raise RuntimeError("visual result frame is not a valid JPEG")

    result_hashes = [str(item.get("sha256")) for item in search["results"]]
    if len(result_hashes) != len(set(result_hashes)):
        raise RuntimeError("visual search returned reviewed exact duplicates")

    print(
        json.dumps(
            {
                "status": "passed",
                "model": status.get("model_id"),
                "model_revision": status.get("model_revision"),
                "canonical_assets_indexed": status.get("assets_ready"),
                "duplicate_aliases": status.get("assets_aliased"),
                "source_frames_indexed": status.get("frames_total"),
                "query": "fighter jet",
                "matched_asset_id": match.get("asset_id"),
                "matched_source_name": match.get("source_name"),
                "source_range_seconds": [match.get("start_seconds"), match.get("end_seconds")],
                "source_frame_verified": True,
                "synthetic_descriptions": False,
                "local_inference": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6E verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
