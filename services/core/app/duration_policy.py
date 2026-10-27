"""Shared duration policy and read-only source-speech estimates. No model calls."""

import math
import re

MAX_EDIT_SECONDS = 120
MODES = {"follow_story", "aim", "strict"}
LEGACY_CEILINGS = {15: 18, 20: 25, 30: 36, 45: 52, 60: 60}


def duration_settings(job):
    return {
        "duration_mode": job.get("duration_mode") or "aim",
        "max_duration_seconds": int(job.get("max_duration_seconds") or 90),
        "target_duration_seconds": int(job.get("target_duration_seconds") or 45),
    }


def apply_duration_snapshot(context, row):
    policy = row.get("duration_policy")
    if isinstance(policy, dict) and policy.get("duration_mode") in MODES:
        context["job"].update(
            {
                key: policy[key]
                for key in (
                    "duration_mode",
                    "max_duration_seconds",
                    "target_duration_seconds",
                )
                if key in policy
            }
        )


def resolve_duration(job):
    target = float(job.get("target_duration_seconds") or 45)
    mode = job.get("duration_mode")
    # Old submitted plans/clients without a policy retain their validation
    # contract. Migrated jobs and all new API jobs explicitly supply a mode.
    if mode not in MODES:
        maximum = LEGACY_CEILINGS.get(target, 60)
        return {
            "mode": "legacy",
            "preferred_seconds": target,
            "maximum_seconds": maximum,
            "absolute_maximum_seconds": MAX_EDIT_SECONDS,
        }
    ceiling = min(MAX_EDIT_SECONDS, max(5, int(job.get("max_duration_seconds") or 90)))
    maximum = min(ceiling, math.ceil(target * 1.2)) if mode == "aim" else ceiling
    return {
        "mode": mode,
        "preferred_seconds": target,
        "maximum_seconds": maximum,
        "absolute_maximum_seconds": MAX_EDIT_SECONDS,
    }


def plan_duration(document):
    return round(
        sum(
            float(
                clip.get("duration")
                or (
                    float(clip.get("source_out") or 0)
                    - float(clip.get("source_in") or 0)
                )
            )
            for clip in document.get("clips", [])
        ),
        6,
    )


def validate_duration(total, job):
    policy = resolve_duration(job)
    maximum = policy["maximum_seconds"]
    if total > maximum + 0.01:
        if policy["mode"] == "legacy":
            if total > 60.01:
                raise ValueError(f"preview duration {total:.3f}s exceeds 60 seconds")
            raise ValueError(
                f"edit duration {total:.3f}s exceeds the {maximum:.3f}s ceiling for a {policy['preferred_seconds']:g}s target"
            )
        raise ValueError(
            f"This edit needs {total:.2f}s; its duration limit is {maximum:g}s. "
            "Increase the maximum or choose Follow the story in Duration settings, "
            "or request a condensed version/split. Required words will not be clipped to fit."
        )


def duration_preflight(context):
    policy = resolve_duration(context["job"])
    seen, speech = set(), 0.0
    for asset in context["assets"]:
        key = asset.get("sha256") or asset["asset_id"]
        if key in seen or asset.get("library_role") == "broll":
            continue
        seen.add(key)
        spans = []
        for segment in asset.get("transcript_segments", []):
            try:
                a, b = float(segment["start"]), float(segment["end"])
            except (TypeError, ValueError, KeyError):
                continue
            if (
                math.isfinite(a + b)
                and 0 <= a < b
                and str(segment.get("text") or "").strip()
            ):
                spans.append((a, b))
        end = -1.0
        for a, b in sorted(spans):
            speech += max(0, b - max(a, end))
            end = max(end, b)
    brief = " ".join(
        [
            str(context["project"].get("brief") or ""),
            str(context["job"].get("must_include") or ""),
        ]
    )
    preserve = bool(
        re.search(
            r"\b(?:use as much.{0,20}speech|(?:all|complete|entire)\s+(?:(?:of\s+)?(?:the|my)\s+)?(?:speech|explanation|points|list)|include all|keep all)\b",
            brief,
            re.I,
        )
    )
    warning = (
        f"The selected sources contain about {speech:.0f}s of transcribed speech, including possible repeated takes. "
        f"Keeping all required points may exceed the {policy['maximum_seconds']:g}s limit. "
        "Check the maximum before starting; this is an estimate, not a required-script measurement."
        if preserve and speech > policy["maximum_seconds"]
        else None
    )
    return {
        **policy,
        "available_speech_seconds": round(speech, 1),
        "preserve_content_requested": preserve,
        "warning": warning,
        "estimate_kind": "transcript_intervals_including_possible_repeated_takes",
        "hosted_model_calls": 0,
    }


def duration_review(context, document):
    policy = resolve_duration(context["job"])
    total = plan_duration(document)
    return {
        **policy,
        "actual_seconds": round(total, 3),
        "above_preferred": total > policy["preferred_seconds"] + 0.01,
        "local_repair": context.get("duration_repair"),
        "hosted_model_calls": 0,
    }
