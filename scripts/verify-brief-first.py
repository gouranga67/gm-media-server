#!/usr/bin/env python3
"""Read-only brief-first deployment contract. Does not create jobs or call AI."""

import json
import runpy
from pathlib import Path


def main():
    helpers = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))
    request = helpers["request"]
    pilot = request("pilot-readiness")
    capability = pilot.get("brief_first_editing") or {}
    if not capability.get("schema_ready") or not capability.get("automatic_assembly"):
        raise RuntimeError("brief-first schema and application build are not deployed")
    if capability.get("extra_classification_calls") != 0 or not capability.get(
        "legacy_engines_preserved"
    ):
        raise RuntimeError("unexpected assembly compatibility contract")
    jobs = request("jobs/manage")
    checked = 0
    for job in jobs:
        if checked >= 5:
            break
        result = request(f"jobs/{job['id']}/assembly")
        if result.get("settings", {}).get("assembly_mode") not in {
            "auto",
            "talking_head",
            "montage",
        }:
            raise RuntimeError("assembly settings are missing")
        decision = result.get("decision")
        if decision and (
            decision.get("recipe") not in {"talking_head", "montage"}
            or decision.get("hosted_model_calls") != 0
        ):
            raise RuntimeError("invalid saved assembly decision")
        checked += 1
    print(
        json.dumps(
            {
                "status": "passed",
                "brief_first_schema": True,
                "inspected_jobs": checked,
                "jobs_created": 0,
                "hosted_model_calls": 0,
                "human_playback_acceptance": "required",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Brief-first verification failed: {error}") from error
