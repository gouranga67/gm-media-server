#!/usr/bin/env python3
"""Verify the source-derived searchable media catalogue."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")


def request(path: str) -> tuple[int, dict | list]:
    http_request = urllib.request.Request(f"{BASE_URL}/{path.lstrip('/')}", method="GET")
    try:
        with urllib.request.urlopen(http_request, timeout=60) as response:
            return response.status, json.load(response)
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


def searchable_token(*values: str) -> str | None:
    for value in values:
        candidates = re.findall(r"[A-Za-z0-9]{3,}", value)
        if candidates:
            return max(candidates, key=len)
    return None


def main() -> int:
    deadline = time.monotonic() + 180
    status = None
    while time.monotonic() < deadline:
        status = require("catalog/status", 200)
        if not isinstance(status, dict):
            raise RuntimeError("catalogue status response is invalid")
        if int(status.get("assets_pending", 0)) == 0:
            break
        time.sleep(2)
    if not isinstance(status, dict) or int(status.get("assets_pending", -1)) != 0:
        raise RuntimeError("catalogue backfill did not finish within three minutes")
    if int(status.get("assets_failed", 0)) != 0:
        raise RuntimeError(f"catalogue contains failed assets: {status['assets_failed']}")
    if int(status.get("assets_total", 0)) == 0 or int(status.get("segments_total", 0)) == 0:
        raise RuntimeError("catalogue contains no indexed source evidence")

    library = require("assets/library?limit=500", 200)
    if not isinstance(library, list) or not library:
        raise RuntimeError("server library contains no analyzed originals")
    hash_counts = Counter(str(item.get("sha256")) for item in library)
    candidate = next(
        (
            item
            for item in library
            if hash_counts[str(item.get("sha256"))] == 1
            and searchable_token(str(item.get("source_name", "")), str(item.get("project_name", "")))
        ),
        library[0],
    )
    token = searchable_token(str(candidate.get("source_name", "")), str(candidate.get("project_name", "")))
    if token is None:
        raise RuntimeError("could not derive a safe catalogue query from the server library")
    parameters = urllib.parse.urlencode({"query": token, "limit": 100})
    search = require(f"catalog/search?{parameters}", 200)
    if not isinstance(search, dict) or not isinstance(search.get("results"), list):
        raise RuntimeError("catalogue search response is invalid")
    result = next(
        (item for item in search["results"] if item.get("asset_id") == candidate.get("id")),
        None,
    )
    if result is None:
        raise RuntimeError("catalogue search did not return its verified source asset")
    required = {
        "segment_id",
        "asset_id",
        "project_id",
        "project_name",
        "source_name",
        "segment_kind",
        "start_seconds",
        "end_seconds",
        "text",
        "source_model",
    }
    if not required.issubset(result):
        raise RuntimeError("catalogue result is missing provenance or time-range evidence")
    if float(result["end_seconds"]) < float(result["start_seconds"]):
        raise RuntimeError("catalogue result contains an invalid source range")

    blank_status, _ = request("catalog/search?query=%20")
    if blank_status != 422:
        raise RuntimeError("blank catalogue queries are not rejected")

    print(
        json.dumps(
            {
                "status": "passed",
                "catalog_version": status.get("catalog_version"),
                "assets_indexed": status.get("assets_ready"),
                "segments_indexed": status.get("segments_total"),
                "transcript_segments": status.get("transcript_segments"),
                "scene_segments": status.get("scene_segments"),
                "query": token,
                "matched_asset_id": candidate.get("id"),
                "matched_segment_kind": result.get("segment_kind"),
                "evidence_model": result.get("source_model"),
                "synthetic_descriptions": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6D verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
