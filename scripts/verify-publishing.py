#!/usr/bin/env python3
"""Read-only publishing readiness. Never connects accounts, generates copy or posts."""

import importlib.util
import json
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "publishing_readiness", Path(__file__).with_name("verify-phase16.py")
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    settings = helper.request("publishing/status")
    accounts = helper.request("publishing/connections")
    drafts = helper.request("publishing/drafts")
    if (
        not isinstance(settings.get("configured"), bool)
        or settings.get("publishes_previews") is not False
    ):
        raise RuntimeError("Invalid publishing configuration response.")
    for account in accounts:
        if any(
            key in account
            for key in ("token", "access_token", "token_ciphertext", "app_secret")
        ):
            raise RuntimeError(
                "Account credentials must never appear in a public response."
            )
        if account.get("platform") not in {"instagram", "facebook"}:
            raise RuntimeError("Unknown publishing platform.")
    for draft in drafts:
        if not draft.get("video_sha256") or int(draft.get("revision", 0)) < 1:
            raise RuntimeError("Posting draft is not pinned to a versioned export.")
        for post in draft.get("posts", []):
            if post["status"] not in {
                "queued",
                "uploading",
                "processing",
                "publishing",
                "published",
                "failed",
                "unknown",
                "cancelled",
            }:
                raise RuntimeError("Unknown publishing state.")
    print(
        json.dumps(
            {
                "status": "passed",
                "meta_configured": settings["configured"],
                "connected_accounts": sum(a["active"] for a in accounts),
                "posting_drafts": len(drafts),
                "model_calls": 0,
                "posts_created": 0,
                "accounts_connected": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit("Publishing verification failed: " + str(error))
