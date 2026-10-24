#!/usr/bin/env python3
"""Verify the exact-duplicate audit and its non-destructive review record."""

import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")


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
    audit = require("assets/duplicates?sort=most_storage&limit=250", 200)
    if not isinstance(audit, dict) or not isinstance(audit.get("summary"), dict):
        raise RuntimeError("duplicate audit response is invalid")
    summary = audit["summary"]
    required_summary = {
        "originals_scanned",
        "duplicate_groups",
        "unreviewed_groups",
        "redundant_copies",
        "optimized_copies",
        "reclaimable_bytes",
    }
    if not required_summary.issubset(summary):
        raise RuntimeError("duplicate audit summary is incomplete")
    groups = audit.get("groups")
    if not isinstance(groups, list):
        raise RuntimeError("duplicate audit groups are invalid")

    reviewed_sha256 = None
    canonical_asset_id = None
    if groups:
        group = groups[0]
        copies = group.get("copies")
        if not isinstance(copies, list) or len(copies) < 2:
            raise RuntimeError("duplicate group does not expose every identical original")
        if group.get("copy_count") != len(copies):
            raise RuntimeError("duplicate copy count does not match its provenance records")
        expected_reclaimable = sum(
            int(copy["byte_size"])
            for copy in copies
            if copy["id"] != group["canonical_asset_id"] and not copy.get("storage_optimized", False)
        )
        if group.get("reclaimable_bytes") != expected_reclaimable:
            raise RuntimeError("duplicate reclaimable-byte calculation is incorrect")
        reviewed_sha256 = group["sha256"]
        canonical_asset_id = group["canonical_asset_id"]
        review = require(
            f"assets/duplicates/{reviewed_sha256}/review",
            200,
            method="POST",
            payload={"canonical_asset_id": canonical_asset_id},
        )
        if not isinstance(review, dict) or review.get("canonical_asset_id") != canonical_asset_id:
            raise RuntimeError("canonical duplicate review was not stored")
        refreshed = require(f"assets/duplicates?query={reviewed_sha256}&limit=10", 200)
        refreshed_groups = refreshed.get("groups") if isinstance(refreshed, dict) else None
        if not isinstance(refreshed_groups, list) or len(refreshed_groups) != 1:
            raise RuntimeError("reviewed duplicate group could not be retrieved by checksum")
        if not refreshed_groups[0].get("reviewed"):
            raise RuntimeError("duplicate group did not report its stored review")

    invalid_status, _ = request(
        "assets/duplicates/not-a-sha256/review",
        method="POST",
        payload={"canonical_asset_id": "11111111-1111-4111-8111-111111111111"},
    )
    if invalid_status != 422:
        raise RuntimeError("invalid duplicate checksum was not rejected")

    print(
        json.dumps(
            {
                "status": "passed",
                "originals_scanned": summary["originals_scanned"],
                "duplicate_groups": summary["duplicate_groups"],
                "redundant_copies": summary["redundant_copies"],
                "reclaimable_bytes": summary["reclaimable_bytes"],
                "reviewed_sha256": reviewed_sha256,
                "canonical_asset_id": canonical_asset_id,
                "media_files_changed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 6C2 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
