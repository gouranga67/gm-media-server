"""One bounded local attempt to fix a small overrun using measured quiet gaps."""

import re
import time
import subprocess
from types import SimpleNamespace

from app.duration_policy import plan_duration, resolve_duration


def repair_duration_overrun(document, context):
    total = plan_duration(document)
    policy = resolve_duration(context["job"])
    maximum = policy["maximum_seconds"]
    report = {
        "before_seconds": total,
        "after_seconds": total,
        "status": "not_needed",
        "hosted_model_calls": 0,
        "measured_gaps": 0,
    }
    if total <= maximum + 0.01 or policy["mode"] == "legacy":
        return document, report
    report["status"] = "no_safe_local_trim"
    editorial = context["job"].get("editorial_policy") or {}
    if (
        total - maximum > 2
        or editorial.get("bloopers_requested")
        or editorial.get("preserve_pauses_requested")
        or context["job"].get("edit_style") == "calm"
    ):
        return document, report
    from app.edit_plan import (
        TalkingHeadEditPlan,
        MontageEditPlan,
        source_word_gaps,
        apply_timeline_adjustments,
    )
    from app.story_finishing import _measure
    from app.config import get_settings

    try:
        model = (
            MontageEditPlan
            if document.get("recipe") == "montage"
            else TalkingHeadEditPlan
        )
        original = model.model_validate(document)
    except ValueError:
        return document, report
    if original.finishing is not None:
        return document, report
    inventory = {str(a["asset_id"]): a for a in context["assets"]}
    candidate = original
    deadline = time.monotonic() + 8
    for _ in range(3):
        needed = plan_duration(candidate.model_dump(mode="json")) - maximum
        gaps = []
        for index, clip in enumerate(candidate.clips):
            asset = inventory.get(str(clip.asset_id), {})
            if (
                not asset.get("_storage_key")
                or not getattr(clip, "include_source_audio", True)
                or re.search(
                    r"\b(pause|hold|reaction|laugh|breathe)\b",
                    clip.editorial_intent,
                    re.I,
                )
            ):
                continue
            for start, end, length in source_word_gaps(
                asset, clip.source_in, clip.source_out
            ):
                if length >= max(1.0, needed + 0.45):
                    gaps.append((length, index, start, min(end, start + 3)))
        if not gaps or time.monotonic() >= deadline:
            break
        changed = False
        for _, index, start, end in sorted(gaps)[:3]:
            remaining = deadline - time.monotonic()
            if remaining <= 0.2:
                break
            asset = inventory[str(candidate.clips[index].asset_id)]
            try:
                measured = _measure(
                    asset,
                    SimpleNamespace(source_in=start, source_out=end),
                    get_settings(),
                    min(2.5, remaining),
                )
                report["measured_gaps"] += 1
                quiet = [
                    [max(start, start + item["start"]), min(end, start + item["end"])]
                    for item in measured["silence_intervals"]
                    if item["end"] - item["start"] >= needed + 0.45
                ]
                if not quiet:
                    continue
                tightened = apply_timeline_adjustments(
                    candidate,
                    [
                        {
                            "clip_index": index,
                            "max_pause_seconds": 0.4,
                            "verified_pause_ranges": quiet,
                        }
                    ],
                    context["assets"],
                )
                duration = plan_duration(tightened.model_dump(mode="json"))
                if duration >= plan_duration(candidate.model_dump(mode="json")):
                    continue
                candidate, changed = tightened, True
                if duration <= maximum + 0.01:
                    report.update(
                        status="trimmed_verified_quiet", after_seconds=duration
                    )
                    return candidate.model_dump(mode="json"), report
                break
            except (
                ValueError,
                OSError,
                RuntimeError,
                KeyError,
                subprocess.SubprocessError,
            ):
                continue
        if not changed:
            break
    return document, report
