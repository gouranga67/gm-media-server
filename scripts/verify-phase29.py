#!/usr/bin/env python3
"""Read-only library intake readiness check; no upload, edit or model request."""
import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability = request("system").get("library_intake") or {}
    schema = request("system/library-intake")
    if capability.get("version") != 1 or not schema.get("schema_ready") or not all(capability.get(key)
            for key in ("durable_registration", "folder_upload", "reviewable_inbox", "server_pagination")):
        raise RuntimeError("deploy Phase 29 and migration 044 before running this check")
    if capability.get("automatic_hosted_model_calls") != 0 or capability.get("upload_concurrency") != 2:
        raise RuntimeError("the bounded local intake contract is incomplete")
    if not schema.get("nested_folders_schema_ready") or schema.get("folder_max_depth") != 4:
        raise RuntimeError("deploy the nested-folder follow-up and migration 048 before running this check")
    folders = request("library/collections")
    from uuid import UUID
    parents = {UUID(folder["id"]): UUID(folder["parent_id"]) if folder.get("parent_id") else None for folder in folders}
    for folder_id in parents:
        current, seen = folder_id, set()
        while current is not None:
            if current not in parents or current in seen or len(seen) >= 4:
                raise RuntimeError("the folder hierarchy has an unavailable parent, cycle or excessive depth")
            seen.add(current)
            current = parents[current]
    for path in ("library/intake?limit=1", "library/browse?limit=1"):
        page = request(path)
        if not isinstance(page.get("items"), list) or len(page["items"]) > 1 or not isinstance(page.get("total"), int):
            raise RuntimeError(f"invalid pagination response: {path}")
    print(json.dumps({"status": "passed", "capability": capability, "schema_ready": True,
        "nested_folders_schema_ready": True, "folder_count": len(folders),
        "read_only": True, "uploads_started": 0, "model_calls": 0,
        "note": "Upload a small mixed batch into a folder, reopen the Inbox, check names/labels and explicitly mark reviewed."}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 29 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
