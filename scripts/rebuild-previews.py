#!/usr/bin/env python3
"""Re-render named jobs with their saved cuts, retaining every previous version."""

import argparse
import runpy
import sys
import time
from pathlib import Path
from uuid import UUID


TIMING_PIPELINE = "frame_sample_clocks_v4"


def rebuild(job_id, request, *, wait_seconds=1800):
    # The running API must advertise the fix before any work is queued.
    if request("system").get("render_timing_pipeline") != TIMING_PIPELINE:
        raise RuntimeError("deploy the timing fix with sudo ./scripts/install-service.sh first")
    review = request(f"jobs/{job_id}/review")
    previous = review.get("latest_run") or {}
    if previous.get("status") != "ready":
        raise RuntimeError("the latest version must be ready; wait for any active work to finish")
    manifest = previous.get("manifest") or {}
    render = manifest.get("render") or {}
    if render.get("timing_pipeline") == TIMING_PIPELINE and render.get("stream_timing_verified"):
        print(f"{job_id}: version {previous['version']} already uses verified timing", flush=True)
        return previous
    plan_hash = manifest.get("edit_plan_sha256")
    if not plan_hash:
        raise RuntimeError("the saved edit has no plan fingerprint; refusing an unverified rebuild")
    run = request(f"jobs/{job_id}/preview/rebuild", method="POST", expected=202)
    print(f"{job_id}: rebuilding version {run['version']} from the saved cut; no AI request", flush=True)
    deadline = time.monotonic() + wait_seconds
    last_status = None
    while time.monotonic() < deadline:
        review = request(f"jobs/{job_id}/review")
        current = next((r for r in review.get("versions", []) if r.get("id") == run["id"]), None)
        if current is None:
            raise RuntimeError("the queued version could not be found")
        state = current.get("status")
        if state != last_status:
            print(f"{job_id}: {state}", flush=True)
            last_status = state
        if state == "failed":
            raise RuntimeError(current.get("error") or "the rebuild failed; the previous version is retained")
        if state == "ready":
            manifest = current.get("manifest") or {}
            render = manifest.get("render") or {}
            if manifest.get("edit_plan_sha256") != plan_hash:
                raise RuntimeError("the rebuilt cut differs from the previous plan; review it before using")
            if render.get("timing_pipeline") != TIMING_PIPELINE or not render.get("stream_timing_verified"):
                raise RuntimeError("the worker has not loaded the timing fix; rebuild the service")
            print(f"PASS  {job_id}: version {current['version']} ready, same cut, verified stream timing", flush=True)
            return current
        time.sleep(3)
    raise RuntimeError("still processing; the server continues working and previous versions remain available")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="+", type=UUID, help="Job IDs to rebuild without new editor requests")
    args = parser.parse_args()
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    failures = 0
    for job_id in dict.fromkeys(args.jobs):
        try:
            rebuild(str(job_id), request)
        except Exception as error:
            failures += 1
            print(f"FAIL  {job_id}: {error}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
