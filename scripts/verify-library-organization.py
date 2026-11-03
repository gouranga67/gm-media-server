#!/usr/bin/env python3
"""Read-only live contracts for auto-sort and photo categories; never calls AI."""
import importlib.util
import json
from pathlib import Path
from uuid import UUID


def main():
    spec = importlib.util.spec_from_file_location("organization_readiness", Path(__file__).with_name("verify-phase16.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assets = helper.request("library/assets?limit=5")
    categories = {"auto","review","product","scene","document","other"}
    for asset in assets:
        if asset.get("media_category") not in categories:
            raise RuntimeError("library media categories are missing or invalid")
    sessions = helper.request("library/organization")
    folders = helper.request("library/collections")
    if not isinstance(folders, list):
        raise RuntimeError("library folders are not a list")
    for folder in folders:
        UUID(folder["id"])
        if not folder.get("name") or int(folder.get("asset_count", -1)) < 0 or "cover_asset_id" not in folder:
            raise RuntimeError("folder browsing contract is incomplete; deploy the current build")
        if folder["cover_asset_id"]:
            UUID(folder["cover_asset_id"])
    if not isinstance(sessions,list):
        raise RuntimeError("auto-sort history is not a list")
    for session in sessions:
        UUID(session["id"])
        detail = helper.request(f"library/organization/{session['id']}")
        if "inventory" in detail or detail["status"] not in ("pending","generating","ready","failed"):
            raise RuntimeError("auto-sort response leaked internal inventory or has invalid status")
        if not 1 <= len(detail["asset_ids"]) <= 24:
            raise RuntimeError("invalid auto-sort batch size")
        if detail["status"] == "ready":
            ids = [item["asset_id"] for item in detail["suggestions"]]
            if len(set(ids)) != len(ids) or set(ids) != set(detail["asset_ids"]):
                raise RuntimeError("auto-sort suggestions do not match their requested originals")
            for item in detail["suggestions"]:
                if not item["display_name"] or item["media_category"] not in categories:
                    raise RuntimeError("invalid suggested name or category")
    print(json.dumps({"status":"passed","checked_assets":len(assets),"folders_checked":len(folders),"saved_auto_sort_sessions":len(sessions),
                      "model_calls":0,"renamed_files":0},indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Library organization verification failed: {error}") from error
