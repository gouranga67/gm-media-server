#!/usr/bin/env python3
"""Read-only Phase 26 deployment contract; no revisions, renders or model calls."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    system = request("system").get("grounded_revisions") or {}
    readiness = request("system/grounded-revisions")
    if system.get("version") != 1 or not readiness.get("schema_ready"):
        raise RuntimeError("deploy this build and migration 043 before running the check")
    if readiness.get("hosted_model_calls") != 0 or not all(readiness.get(key) for key in (
        "quoted_phrase_audio", "verified_quiet_pause", "frozen_resolution", "subtitle_corrections_retimed")):
        raise RuntimeError("the grounded revision contract is incomplete")
    print(json.dumps({"status": "passed", "capabilities": readiness, "read_only": True,
        "revisions_queued": 0, "renders_started": 0, "note": "Real-footage revision and story acceptance remains a playback check."}, indent=2))
    print("PASS  Grounded revision schema and deployment contract; no editing work started.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 26 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
