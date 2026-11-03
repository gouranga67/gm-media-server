#!/usr/bin/env python3
"""Read-only visual finishing deployment check; never requests a new render."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability = request("system").get("visual_finishing") or {}
    if capability.get("version") != "selected_visual_v1" or capability.get("detector") != "yunet_2023mar" or not all(capability.get(k) for k in (
        "single_face_follow", "small_exposure_match", "explicit_opt_in", "resolved_caption_avoidance")):
        raise RuntimeError("deploy the Phase 28 build before running this check")
    if capability.get("hosted_model_calls") != 0 or capability.get("max_clips") != 8 or capability.get("inspection_budget_seconds") != 20:
        raise RuntimeError("the bounded local visual finishing contract is incomplete")
    print(json.dumps({"status": "passed", "capability": capability, "read_only": True,
        "renders_started": 0, "model_calls": 0,
        "note": "Deployment contract only. Turn on the optional tools in a new visual preview and inspect actual motion, product visibility and card readability."}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 28 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
