#!/usr/bin/env python3
"""Read-only subtitle editor readiness. Never saves text or starts a render."""
import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability = request("system").get("subtitle_editor") or {}
    if capability.get("version") != 1 or not capability.get("explicit_draft_and_apply"):
        raise RuntimeError("deploy the subtitle editor build before running this check")
    checked = None
    for job in (request("usage?days=0").get("job_history") or [])[:30]:
        review = request(f"jobs/{job['id']}/review")
        run = review.get("latest_run") or {}
        if run.get("status") != "ready":
            continue
        draft = request(f"jobs/{job['id']}/edits/{run['id']}/subtitles")
        if draft.get("hosted_model_calls") != 0 or not isinstance(draft.get("cues"), list):
            raise RuntimeError("subtitle draft response is invalid")
        checked = {"job_id": job["id"], "version": run["version"], "caption_cards": len(draft["cues"])}
        break
    print(json.dumps({"status": "passed", "capability": capability, "checked": checked,
        "read_only": True, "draft_writes": 0, "renders_started": 0}, indent=2))
    print("PASS  Subtitle editor installed; draft saving and applying remain explicit user actions.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Subtitle editor verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
