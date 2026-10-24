#!/usr/bin/env python3
"""Queue a reproducible local visual-index rebuild."""

import argparse
import json
import os
import urllib.parse
import urllib.request
from uuid import UUID


BASE_URL = os.environ.get("GM_MEDIA_URL", "http://127.0.0.1:3000/api/media").rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", help="Queue only one canonical asset UUID")
    arguments = parser.parse_args()
    parameters = ""
    if arguments.asset_id:
        asset_id = str(UUID(arguments.asset_id))
        parameters = "?" + urllib.parse.urlencode({"asset_id": asset_id})
    request = urllib.request.Request(
        f"{BASE_URL}/catalog/visual/reindex{parameters}",
        data=b"{}",
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
