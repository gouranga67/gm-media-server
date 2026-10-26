"""Conservative source-timed cutaway hints; no face or lip-reading claims."""

import math
from typing import Any


def speech_ranges(asset: dict[str, Any]) -> list[tuple[float, float]]:
    intervals = []
    for segment in asset.get("transcript_segments", []):
        if not isinstance(segment, dict):
            continue
        words = segment.get("words") or []
        valid = []
        for item in words:
            if not isinstance(item, dict) or not str(item.get("text") or item.get("word") or "").strip():
                continue
            try:
                start, end = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(start) and math.isfinite(end) and end > start:
                valid.append((max(0, start - 0.15), end + 0.15))
        if valid:
            intervals.extend(valid)
        elif str(segment.get("text") or "").strip():
            try:
                start, end = float(segment["start"]), float(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(start) and math.isfinite(end) and end > start:
                intervals.append((max(0, start - 0.15), end + 0.15))
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def broll_guidance(asset: dict[str, Any]) -> dict[str, Any]:
    if str(asset.get("mime_type") or "").startswith("image/"):
        return {"kind": "still_candidate", "note": "Inspect the supplied picture for subject relevance and legibility."}
    intervals = speech_ranges(asset)
    duration = float(asset.get("duration_seconds") or 0)
    windows = []
    cursor = 0.0
    for start, end in intervals:
        if min(start, duration) - cursor >= 0.5:
            windows.append({"source_in": round(cursor, 3), "source_out": round(min(start, duration), 3)})
        cursor = max(cursor, end)
    if duration - cursor >= 0.5:
        windows.append({"source_in": round(cursor, 3), "source_out": round(duration, 3)})
    return {
        "kind": "speech_present" if intervals else "no_transcribed_speech",
        "speech_free_windows": sorted(sorted(windows, key=lambda item: item["source_out"] - item["source_in"], reverse=True)[:8],
                                      key=lambda item: item["source_in"]),
        "note": "Speech timing only, not a face detector. Verify the picture; never overlay visibly different speaking over the main voice.",
    }


def guard_broll(plan: Any, assets: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    """Drop risky new cues locally; do not invent replacements or recut speech."""
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    kept, removed = [], []
    for cue in plan.broll:
        asset = inventory.get(str(cue.asset_id))
        # Unknown IDs and malformed media still go to the normal validator.
        if asset is not None and cue.media_kind == "video" and any(
            start < cue.source_out - 0.001 and end > cue.source_in + 0.001 for start, end in speech_ranges(asset)
        ):
            removed.append({"asset_id": str(cue.asset_id), "source_in": cue.source_in, "source_out": cue.source_out,
                            "start_seconds": cue.start_seconds, "reason": "source_speech_overlaps_silent_cutaway"})
        else:
            kept.append(cue)
    return plan.model_copy(update={"broll": kept}, deep=True), removed
