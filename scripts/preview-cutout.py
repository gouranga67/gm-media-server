#!/usr/bin/env python3
"""Run one bounded local comparison in the worker; leave the edit unchanged."""
import argparse
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
from uuid import UUID


def command(args):
    if type(args.clip) is not int or not 1 <= args.clip <= 48 or not math.isfinite(args.offset) or not 0 <= args.offset <= 86400 or (args.seconds is not None and (not math.isfinite(args.seconds) or not .5 <= args.seconds <= 3)):
        raise ValueError("choose clip 1–48, a finite nonnegative offset and a 0.5–3 second sample")
    values = ["docker", "compose", "exec", "-T", "worker", "python", "-m", "app.cutout_lab",
        "--job", str(args.job), "--clip", str(args.clip), "--offset", str(args.offset)]
    if args.seconds is not None:
        values += ["--seconds", str(args.seconds)]
    return values


def main():
    parser = argparse.ArgumentParser(description="Make a silent background-cutout test from a ready edit, with no edit/export/hosted AI request.")
    parser.add_argument("job", type=UUID, help="job ID from the GM Studio URL")
    parser.add_argument("--clip", type=int, required=True, help="main-picture clip number, starting at 1")
    parser.add_argument("--offset", type=float, default=0, help="seconds into that shot")
    parser.add_argument("--seconds", type=float, default=None, help="0.5–3 seconds; default up to 2 seconds")
    args = parser.parse_args()
    print("Making a sampled cutout comparison. Your edit and originals stay unchanged.", flush=True)
    result = subprocess.run(command(args), cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=35)
    if result.returncode:
        print("Cutout comparison did not finish. Deploy the current worker, choose a ready edit and a normal-speed video shot of at least 0.5 seconds, then try again. Docker access may require sudo. The edit is unchanged.", file=sys.stderr)
        return 1
    report = json.loads(result.stdout)
    if report.get("version") != "person_cutout_lab_v1" or report.get("eligible_for_edit_application") is not False or report.get("quality_approved") is not False or report.get("sample", {}).get("job_id") != str(args.job):
        raise ValueError("worker returned an unexpected comparison report")
    key = report["cache_key"]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("worker returned an invalid comparison identifier")
    base = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["BASE"]
    url = f"{base}/jobs/{args.job}/cutout-lab/{key}"
    print(f"\nOpen on your laptop/phone while connected to Tailscale:\nComparison video: {url}/comparison.mp4\nStill comparisons: {url}/contact.png\nFirst transparent image: {url}/matte.png\nMeasurements: {url}/report.json")
    print("\nThis is a silent, sampled 8 fps test, not a finished edit. Inspect hair, hands, the full held product, background holes and flicker. Nothing is applied to a reel.")
    metrics = report.get("metrics", {})
    print(f"Local processing: {metrics.get('processing_seconds', '?')}s · {metrics.get('sampled_frames', '?')} sampled frames · zero hosted AI calls.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Cutout comparison could not be read or exceeded its time budget. The existing edit is unchanged.", file=sys.stderr)
        raise SystemExit(1)
