#!/usr/bin/env python3
"""Read-only deployment checks for the continuous studio sprint. No model calls."""

import json
import runpy
import sys
from pathlib import Path


def main():
    helpers = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))
    request = helpers["request"]
    pilot = request("pilot-readiness")
    if not pilot.get("schema_ready") or pilot.get("version") != "19-25.1":
        raise RuntimeError("the continuous sprint schema/build is not deployed")
    knowledge = request("library/knowledge")
    if (
        knowledge.get("evidence_version") != "1.0"
        or len(knowledge.get("products", [])) > 100
    ):
        raise RuntimeError("source knowledge contract is unavailable")
    performance = request("system/performance")
    if len(performance.get("events", [])) > 240:
        raise RuntimeError("worker measurements exceeded the retention bound")
    lab = request("learning/lab")
    if lab.get("hosted_model_calls") != 0:
        raise RuntimeError("the learning dashboard must not make hosted model calls")
    if any(
        item.get("status") not in ("proposed", "promoted", "rolled_back")
        for item in lab.get("lessons", [])
    ):
        raise RuntimeError("unexpected lesson promotion state")
    print(
        json.dumps(
            {
                "status": "passed",
                "phase": "19-25 source deployment",
                "source_knowledge_verified": True,
                "bounded_performance_history": True,
                "evaluated_learning_verified": True,
                "enabled_tools": sum(pilot["tools"].values()),
                "hosted_model_calls": 0,
                "human_playback_and_pilot_acceptance": "required",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Continuous sprint verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
