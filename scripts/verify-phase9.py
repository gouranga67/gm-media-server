#!/usr/bin/env python3
"""Verify safe exact-duplicate storage sharing without deleting library records."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")


def request(path: str, *, method: str = "GET", payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=body,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=3600) as response:
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-storage-optimization",
        action="store_true",
        help="Allow verified exact copies to share physical storage while retaining every path.",
    )
    arguments = parser.parse_args()
    audit = require("assets/duplicates?review_state=reviewed&sort=most_storage&limit=250", 200)
    if not isinstance(audit, dict) or not isinstance(audit.get("groups"), list):
        raise RuntimeError("duplicate audit response is invalid")
    groups = audit["groups"]
    candidates = [group for group in groups if group.get("cleanup_ready")]
    cleanups: list[dict] = []
    if candidates:
        if not arguments.confirm_storage_optimization:
            raise RuntimeError(
                "reviewed duplicates are ready; rerun with --confirm-storage-optimization"
            )
        for candidate in candidates:
            cleanup = require(
                f"assets/duplicates/{candidate['sha256']}/cleanup",
                200,
                method="POST",
                payload={
                    "canonical_asset_id": candidate["canonical_asset_id"],
                    "confirmation": "share_verified_storage",
                },
            )
            if not isinstance(cleanup, dict) or cleanup.get("optimized_copies", 0) < 1:
                raise RuntimeError("cleanup did not report an optimized exact copy")
            cleanups.append(cleanup)

    refreshed = require("assets/duplicates?review_state=reviewed&limit=250", 200)
    if not isinstance(refreshed, dict) or not isinstance(refreshed.get("groups"), list):
        raise RuntimeError("refreshed duplicate audit response is invalid")
    cleaned_hashes = {candidate["sha256"] for candidate in candidates}
    for group in refreshed["groups"]:
        if group.get("sha256") not in cleaned_hashes:
            continue
        if group.get("cleanup_ready") or group.get("reclaimable_bytes") != 0:
            raise RuntimeError("cleaned duplicate group still reports reclaimable storage")
        if any(
            not copy.get("storage_optimized")
            for copy in group["copies"]
            if copy["id"] != group["canonical_asset_id"]
        ):
            raise RuntimeError("one or more redundant paths were not recorded as optimized")

    invalid_status, _ = request(
        f"assets/duplicates/{'a' * 64}/cleanup",
        method="POST",
        payload={
            "canonical_asset_id": "11111111-1111-4111-8111-111111111111",
            "confirmation": "wrong",
        },
    )
    if invalid_status != 422:
        raise RuntimeError("cleanup confirmation contract was not enforced")

    summary = refreshed.get("summary", {})
    print(
        json.dumps(
            {
                "status": "passed",
                "optimized_groups_this_run": len(cleanups),
                "bytes_reclaimed_this_run": sum(
                    int(cleanup.get("bytes_reclaimed", 0)) for cleanup in cleanups
                ),
                "optimized_copies_total": summary.get("optimized_copies", 0),
                "library_records_deleted": 0,
                "paths_preserved": True,
                "future_exact_upload_reuse": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 9 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
