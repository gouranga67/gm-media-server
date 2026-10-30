"""Bounded, local finishing for new ordinary speech stories; never a repair loop."""

import math
import re
import statistics
import time

from app.edit_plan import (
    TalkingHeadEditPlan,
    apply_timeline_adjustments,
    source_word_gaps,
    _tighten_clip_pauses,
)
from app.creative_selection import only_creative_treatments
from app.media_analysis import resolve_source, run_command
from app.quality_review import parse_render_measurements

MAX_MEASURED_CLIPS = 6
MAX_MEASURED_SECONDS = 12
ANALYSIS_BUDGET_SECONDS = 8


def _clip_words(asset: dict, clip) -> list[dict]:
    result = []
    for segment in asset.get("transcript_segments", []):
        for word in segment.get("words", []):
            try:
                start, end = float(word["start"]), float(word["end"])
            except (ValueError, TypeError, KeyError):
                continue
            if (
                math.isfinite(start + end)
                and start < end
                and clip.source_in <= (start + end) / 2 < clip.source_out
            ):
                result.append(word)
    return result


def _measure(asset: dict, clip, settings, timeout: float) -> dict:
    source = resolve_source(settings.media_root, asset["_storage_key"])
    duration = float(clip.source_out - clip.source_in)
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
            "-ss",
            str(clip.source_in),
            "-t",
            str(duration),
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            "silencedetect=noise=-42dB:d=0.7,loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=timeout,
    )
    if result.returncode:
        raise ValueError("passage audio measurement failed")
    return parse_render_measurements(result.stderr, duration)


def _disposable_opening(plan, inventory: dict) -> bool:
    if len(plan.clips) < 2:
        return False
    clip = plan.clips[0]
    words = _clip_words(inventory.get(str(clip.asset_id), {}), clip)
    text = " ".join(str(w.get("text", w.get("word", ""))).strip() for w in words)
    return bool(
        words
        and clip.source_out - clip.source_in <= 1.2
        and re.fullmatch(r"(?:all right|alright|okay|ok|um|uh)[,.!? ]*", text, re.I)
    )


def finish_new_story(context: dict, plan) -> tuple:
    report = {
        "version": 1,
        "status": "not_applicable",
        "changes": [],
        "findings": [],
        "measured_clips": 0,
        "hosted_model_calls": 0,
        "semantic_judgement": "human_review_required",
    }
    job = context["job"]
    policy = job.get("editorial_policy") or {}
    if (
        not isinstance(plan, TalkingHeadEditPlan)
        or policy.get("intent") != "story"
        or policy.get("bloopers_requested")
        or policy.get("preserve_pauses_requested")
        or job.get("edit_style") == "calm"
        or (plan.finishing is not None and not only_creative_treatments(plan.finishing))
    ):
        return plan, report
    started = time.monotonic()
    report["speech_clip_count"] = len(plan.clips)
    inventory = {str(a["asset_id"]): a for a in context["assets"]}
    instructions = " ".join(
        str(context.get("project", {}).get("brief") or "").lower().split()
    )
    preserve_audio = bool(
        re.search(
            r"\b(?:whisper|whispering|quiet|softly|original audio|preserve.*(?:audio|volume))\b",
            instructions,
        )
    )
    preserve_opening = bool(
        re.search(
            r"\b(?:keep|preserve|start with|open with)\b.{0,45}\b(?:all right|alright|okay|um|uh)\b",
            instructions,
        )
    )
    adjustments = {}
    if not preserve_opening and _disposable_opening(plan, inventory):
        adjustments[0] = {"clip_index": 0, "action": "remove"}
        report["changes"].append(
            "Removed a disposable opening fragment; retained the following recorded sentence."
        )
    candidates = []
    for index, clip in enumerate(plan.clips):
        asset = inventory.get(str(clip.asset_id), {})
        if (
            index in adjustments
            or not asset.get("_storage_key")
            or not _clip_words(asset, clip)
            or clip.source_out - clip.source_in > MAX_MEASURED_SECONDS
        ):
            continue
        candidates.append(index)
    # Endings are often from another microphone/take; keep coverage balanced.
    selected = (
        sorted(
            {
                candidates[
                    round(
                        i
                        * (len(candidates) - 1)
                        / (min(MAX_MEASURED_CLIPS, len(candidates)) - 1)
                    )
                ]
                for i in range(min(MAX_MEASURED_CLIPS, len(candidates)))
            }
        )
        if len(candidates) > 1
        else candidates
    )
    measurements = {}
    from app.config import get_settings

    settings = get_settings() if selected else None
    for index in selected:
        remaining = ANALYSIS_BUDGET_SECONDS - (time.monotonic() - started)
        if remaining <= 0.2:
            report["findings"].append(
                "Local audio inspection reached its budget; remaining passages were preserved."
            )
            break
        clip = plan.clips[index]
        try:
            measured = _measure(
                inventory[str(clip.asset_id)], clip, settings, min(3, remaining)
            )
        except Exception:
            report["findings"].append(
                f"Clip {index + 1}: audio inspection unavailable; preserved its timing and level."
            )
            continue
        measurements[index] = measured
        report["measured_clips"] += 1
        verified = []
        if re.search(
            r"\b(?:hold|breathe|reaction|laugh|pause)\b",
            str(clip.editorial_intent).lower(),
        ):
            continue
        gaps = source_word_gaps(
            inventory[str(clip.asset_id)], clip.source_in, clip.source_out
        )
        for quiet in measured["silence_intervals"]:
            for left, right, _ in gaps:
                start = max(left, clip.source_in + quiet["start"])
                end = min(right, clip.source_in + quiet["end"])
                if end - start >= 1.5:
                    verified.append([start, end])
        if verified:
            tightened = _tighten_clip_pauses(
                plan, clip, inventory[str(clip.asset_id)], 0.6, verified
            )
            if len(tightened) != 1 or (
                tightened[0].source_in,
                tightened[0].source_out,
            ) != (clip.source_in, clip.source_out):
                adjustments[index] = {
                    "clip_index": index,
                    "max_pause_seconds": 0.6,
                    "verified_pause_ranges": verified,
                }
                report["changes"].append(
                    f"Clip {index + 1}: shortened a measured quiet interval between recorded words."
                )
    levels = [
        m["loudness"]["integrated_lufs"]
        for m in measurements.values()
        if "integrated_lufs" in m["loudness"]
    ]
    reference = statistics.median(levels) if len(levels) >= 2 else None
    if reference is not None and not preserve_audio:
        for index, measured in measurements.items():
            loudness = measured["loudness"]
            level, peak = (
                loudness.get("integrated_lufs"),
                loudness.get("true_peak_dbfs"),
            )
            clip = plan.clips[index]
            if (
                level is None
                or peak is None
                or reference - level < 8
                or clip.source_audio_gain_db != 0
            ):
                continue
            gain = round(min(6.0, reference - level, -2.0 - peak), 1)
            if gain < 1:
                report["findings"].append(
                    f"Clip {index + 1}: speech is quieter, but measured peaks leave insufficient headroom for an automatic boost."
                )
                continue
            adjustments.setdefault(index, {"clip_index": index})[
                "source_audio_gain_db"
            ] = gain
            report["changes"].append(
                f"Clip {index + 1}: raised its measured quiet source speech by {gain:g} dB; kept the same take."
            )
    result = plan
    if adjustments:
        try:
            result = apply_timeline_adjustments(
                plan,
                [adjustments[i] for i in sorted(adjustments, reverse=True)],
                context["assets"],
            )
            if not preserve_opening and _disposable_opening(result, inventory):
                result = apply_timeline_adjustments(
                    result, [{"clip_index": 0, "action": "remove"}], context["assets"]
                )
                report["changes"].append(
                    "Removed a disposable opening fragment exposed by verified silence cleanup."
                )
        except ValueError:
            result = plan
            report["changes"] = []
            report["findings"].append(
                "Cleanup exceeded safe timeline bounds; preserved the original plan."
            )
    report["status"] = "attention" if report["findings"] else "checked"
    report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result, report
