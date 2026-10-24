#!/usr/bin/env python3
"""Verify reversible media-library organization without deleting originals."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4


def configured_base_url() -> str:
    explicit = os.environ.get("GM_MEDIA_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    environment_file = Path(__file__).resolve().parents[1] / ".env"
    if environment_file.is_file():
        values: dict[str, str] = {}
        for raw_line in environment_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        if values.get("TAILSCALE_AUTH_REQUIRED", "").lower() == "true" and values.get("APP_ORIGIN"):
            return f"{values['APP_ORIGIN'].rstrip('/')}/api/media"

    return "http://127.0.0.1:3000/api/media"


BASE_URL = configured_base_url()


def request(
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict | list | bytes | None]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=body,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            if response.status == 204:
                return response.status, None
            if response.headers.get_content_type() == "application/json":
                return response.status, json.load(response)
            return response.status, response.read()
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
    assets = require("library/assets?state=all&limit=500", 200)
    if not isinstance(assets, list) or not assets:
        raise RuntimeError("managed media library contains no analyzed originals")
    asset = next((item for item in assets if item.get("library_status") == "active"), assets[0])
    asset_id = str(asset["id"])
    detail = require(f"library/assets/{asset_id}", 200)
    if not isinstance(detail, dict) or not isinstance(detail.get("asset"), dict):
        raise RuntimeError("library asset detail response is invalid")
    original = detail["asset"]
    original_hash = str(original["sha256"])
    collection_id = None
    metadata_changed = False
    state_changed = False

    try:
        test_tags = list(original.get("tags", []))
        if "phase-8-verified" not in test_tags:
            test_tags.append("phase-8-verified")
        updated = require(
            f"library/assets/{asset_id}",
            200,
            method="PATCH",
            payload={
                "display_name": original["display_name"],
                "notes": original.get("notes", ""),
                "favorite": bool(original.get("favorite", False)),
                "tags": test_tags,
            },
        )
        metadata_changed = True
        if not isinstance(updated, dict) or "phase-8-verified" not in updated.get("tags", []):
            raise RuntimeError("library metadata update was not stored")
        if updated.get("sha256") != original_hash:
            raise RuntimeError("metadata update changed original provenance")

        collection = require(
            "library/collections",
            201,
            method="POST",
            payload={"name": f"Phase 8 verification {str(uuid4())[:8]}", "description": "Temporary reversible acceptance record"},
        )
        if not isinstance(collection, dict):
            raise RuntimeError("collection create response is invalid")
        collection_id = str(collection["id"])
        require(f"library/collections/{collection_id}/assets/{asset_id}", 204, method="PUT", payload={})
        attached = require(f"library/assets/{asset_id}", 200)
        if not isinstance(attached, dict) or not any(item.get("id") == collection_id for item in attached.get("collections", [])):
            raise RuntimeError("collection membership was not visible on the original")
        require(f"library/collections/{collection_id}/assets/{asset_id}", 204, method="DELETE")

        if original.get("library_status") == "active":
            archived = require(f"library/assets/{asset_id}/archive", 200, method="POST", payload={})
            state_changed = True
            if not isinstance(archived, dict) or archived.get("library_status") != "archived":
                raise RuntimeError("original was not reversibly archived")
            archived_detail = require(f"library/assets/{asset_id}", 200)
            if not isinstance(archived_detail, dict) or archived_detail["asset"].get("sha256") != original_hash:
                raise RuntimeError("archived original was not retained with its provenance")
            require(f"library/assets/{asset_id}/restore", 200, method="POST", payload={})
            state_changed = False

        preview_status, preview = request(f"library/assets/{asset_id}/preview")
        if preview_status != 200 or not isinstance(preview, bytes) or not preview:
            raise RuntimeError("managed original preview could not be downloaded")
    finally:
        if state_changed:
            request(f"library/assets/{asset_id}/restore", method="POST", payload={})
        if metadata_changed:
            request(
                f"library/assets/{asset_id}",
                method="PATCH",
                payload={
                    "display_name": original["display_name"],
                    "notes": original.get("notes", ""),
                    "favorite": bool(original.get("favorite", False)),
                    "tags": original.get("tags", []),
                },
            )
        if collection_id:
            request(f"library/collections/{collection_id}", method="DELETE")

    restored = require(f"library/assets/{asset_id}", 200)
    if not isinstance(restored, dict) or restored["asset"].get("sha256") != original_hash:
        raise RuntimeError("verification cleanup did not preserve the original")

    print(
        json.dumps(
            {
                "status": "passed",
                "asset_id": asset_id,
                "sha256_preserved": True,
                "metadata_round_trip": True,
                "collection_round_trip": True,
                "archive_restore_round_trip": original.get("library_status") == "active",
                "preview_verified": True,
                "originals_deleted": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 8 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
