#!/usr/bin/env python3
"""Read-only evaluation readiness. Never saves a score, spends tokens or promotes a rule."""
import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability = request("system").get("learning_evaluation") or {}
    schema = request("system/learning-evaluation")
    if capability.get("version") != 2 or not schema.get("schema_ready") or not all(capability.get(key)
            for key in ("saved_test_cases","recording_groups","paired_checklist","usage_qualification","promotion_history")):
        raise RuntimeError("deploy Phase 30 and migration 045 before running this check")
    if capability.get("automatic_paid_trials") is not False or capability.get("automatic_promotion") is not False:
        raise RuntimeError("learning trials and promotion must remain explicit owner actions")
    if not schema.get("comparison_history_schema_ready") or not all(capability.get(key) for key in ("complete_trial_readiness","comparison_history_pagination")):
        raise RuntimeError("deploy complete-history evaluation readiness and migration 049 before running this check")
    lab = request("learning/lab")
    if lab.get("version") != 3 or not isinstance(lab.get("cases"),list) or not isinstance(lab.get("history"),list):
        raise RuntimeError("the saved-case evaluation response is incomplete")
    for lesson in lab["lessons"]:
        if lesson.get("evaluation",{}).get("history_scope") != "all_saved_trials":
            raise RuntimeError("readiness must cover every saved trial, not only the displayed page")
    if lab["lessons"]:
        page = request(f"learning/lab/lessons/{lab['lessons'][0]['id']}/comparisons?limit=1")
        if not isinstance(page.get("items"),list) or len(page["items"])>1 or page.get("hosted_model_calls") != 0:
            raise RuntimeError("comparison history must be bounded and read-only")
    print(json.dumps({"status":"passed","read_only":True,"saved_cases":len(lab["cases"]),
        "lessons":len(lab["lessons"]),"promotion_events":len(lab["history"]),"complete_trial_readiness":True,"model_calls":0,
        "note":"Readiness only. Save independent playback tasks, explicitly run trials and review the exact pairs before promotion."},indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 30 verification failed: {error}",file=sys.stderr)
        raise SystemExit(1)
