#!/usr/bin/env python3
"""Read-only acceptance of a local rendered-quality report; never calls an editor."""

import argparse
import importlib.util
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", help="inspect this job's latest preview")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("phase16_requests", Path(__file__).with_name("verify-phase16.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if args.job_id:
        jobs = [{"id": args.job_id}]
    else:
        jobs = [job for job in helper.request("usage?days=0").get("job_history", [])
                if job.get("history_kind") == "editing"][:20]
    for job in jobs:
        review = helper.request(f"jobs/{job['id']}/review")
        run = review.get("latest_run") or {}
        report = (run.get("manifest") or {}).get("quality_review")
        if not report:
            continue
        if run.get("status") != "ready":
            raise RuntimeError("the inspected preview is not ready")
        if report.get("scope") != "rendered_media_and_timing" or report.get("version") != "1.0":
            raise RuntimeError("the quality report has an unsupported scope or version")
        if report.get("hosted_model_calls") != 0 or report.get("additional_model_tokens") != 0:
            raise RuntimeError("local inspection must not use hosted model tokens")
        if report.get("automatic_changes") != []:
            raise RuntimeError("report-only inspection must preserve the edit")
        if report.get("status") not in {"passed", "attention", "incomplete"}:
            raise RuntimeError("the quality report has an unknown status")
        checks, findings = report.get("checks"), report.get("findings")
        if not isinstance(checks, list) or not checks or not isinstance(findings, list):
            raise RuntimeError("the quality report must contain explicit checks and findings")
        print(json.dumps({"status": "passed", "job_id": job["id"], "version": run["version"],
            "review_status": report["status"], "checks": len(checks), "findings": report["finding_count"],
            "render_decode_verified": any(c.get("code") == "decode" and c.get("status") == "passed" for c in checks),
            "automatic_changes": 0, "additional_model_tokens": 0,
            "notice": "Acceptance checks report integrity; it does not certify story quality or clear the listed findings."}, indent=2))
        return
    raise RuntimeError("No quality report is available yet. Create a new preview or use Re-render exact edit after deploying, then rerun this check.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Phase 17 verification failed: {error}") from error
