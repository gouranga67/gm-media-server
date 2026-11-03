#!/usr/bin/env python3
"""Read-only release evidence. Never posts, runs a drill or records acceptance."""
import argparse
import json
from pathlib import Path
import runpy
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-private",action="store_true",help="fail unless private pilot acceptance is complete")
    parser.add_argument("--require-publishing",action="store_true",help="fail unless real publishing acceptance is complete")
    args=parser.parse_args()
    request=runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability=request("system").get("release_acceptance") or {}
    report=request("release/readiness")
    if capability.get("version") != 1 or report.get("version") != 1 or not report.get("schema_ready"):
        raise RuntimeError("deploy Phase 31 and migration 046 before running this check")
    if capability.get("automatic_posts") is not False or report.get("automatic_posts") != 0 or report.get("automatic_model_calls") != 0:
        raise RuntimeError("readiness must not post or run a model")
    if report.get("public_customer_launch_ready") is not False or not isinstance(report.get("checks"),list):
        raise RuntimeError("the private-studio acceptance contract is incomplete")
    result={"status":"passed","read_only":True,"build_id":report["build_id"],
        "private_pilot_complete":report["private_pilot_complete"],"publishing_acceptance_complete":report["publishing_acceptance_complete"],
        "pending_machine_checks":[item["key"] for item in report["technical"] if item["status"] != "pass"],
        "unpassed_human_checks":[item["key"] for item in report["checks"] if not item.get("observation") or not (
            item["observation"]["result"] == "pass" or item.get("allow_na") and item["observation"]["result"] == "not_applicable")],
        "model_calls":0,"posts_created":0,"acceptance_writes":0}
    print(json.dumps(result,indent=2))
    if args.require_private and not report["private_pilot_complete"]:
        raise RuntimeError("private pilot acceptance still needs recorded checks; open Studio → Pilot acceptance")
    if args.require_publishing and not report["publishing_acceptance_complete"]:
        raise RuntimeError("publishing acceptance still needs configuration and real approved-post checks")


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"Phase 31 verification failed: {error}",file=sys.stderr)
        raise SystemExit(1)
