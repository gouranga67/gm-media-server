#!/usr/bin/env python3
"""Read-only acceptance of a rendered High impact job; creates no AI requests."""

import argparse
import importlib.util
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("phase16_requests", Path(__file__).with_name("verify-phase16.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    jobs = [{"id": args.job_id}] if args.job_id else [job for job in helper.request("usage?days=0").get("job_history", [])
        if job.get("history_kind") == "editing"][:30]
    for job in jobs:
        review = helper.request(f"jobs/{job['id']}/review")
        run = review.get("latest_run") or {}
        manifest = run.get("manifest") or {}
        finishing = manifest.get("finishing") or {}
        if finishing.get("mode") != "high_impact":
            continue
        if run.get("status") != "ready":
            raise RuntimeError("the High impact preview is not ready")
        if not finishing.get("dialogue_timeline_preserved") or finishing.get("additional_model_calls") != 0:
            raise RuntimeError("the finishing layer must preserve the base dialogue and add no separate model call")
        overlays = manifest.get("broll") or []
        if len(overlays) > 8 or any(item.get("source_audio_used") is not False for item in overlays):
            raise RuntimeError("B-roll must remain a bounded picture-only layer")
        timeline = sum(float(clip["duration"]) for clip in review.get("editorial_timeline", []))
        previous_end = 0.0
        for cue in sorted(overlays, key=lambda item: item["start_seconds"]):
            start, duration = float(cue["start_seconds"]), float(cue["duration_seconds"])
            if duration < 0.5 or duration > 4 or start < previous_end - 0.001 or start + duration > timeline + 0.01:
                raise RuntimeError("B-roll has invalid or overlapping timeline coverage")
            previous_end = start + duration
        if sum(float(cue["duration_seconds"]) for cue in overlays) > timeline * 0.6 + 0.01:
            raise RuntimeError("B-roll covers too much of the main story")
        print(json.dumps({"status": "passed", "job_id": job["id"], "version": run["version"],
            "rhythmic_picture_changes": len(finishing.get("rhythmic_punch_beats") or []),
            "broll_cutaways": len(overlays), "creative_effects": len(manifest.get("creative_effects") or []),
            "dialogue_timeline_preserved": True, "additional_finishing_model_calls": 0,
            "job_tokens": (review.get("usage") or {}).get("total_tokens", 0),
            "notice": "Checks the finishing plan and manifest. Review relevance, framing, and the finished story by watching the reel."}, indent=2))
        return
    raise RuntimeError("Create a fresh job with the High impact editing style after deploying, then rerun this check.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"High impact verification failed: {error}") from error
