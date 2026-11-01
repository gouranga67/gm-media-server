from typing import Any


def compare_revision(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare executable edit choices, ignoring the model's descriptive prose."""
    def cuts(document: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (str(clip.get("asset_id")), round(float(clip.get("source_in", 0)), 3),
             round(float(clip.get("source_out", 0)), 3),
             round(float(clip.get("duration", 0)), 3))
            for clip in document.get("clips", [])
        ]

    before, after = cuts(previous), cuts(current)
    added = sum(cut not in before for cut in after)
    removed = sum(cut not in after for cut in before)
    changes = []
    if before != after:
        changes.append(f"Source selections/order changed: {added} new or retimed, {removed} replaced or removed.")
        for index, (old, new) in enumerate(zip(before, after, strict=False)):
            if old[0] == new[0] and old[1:3] != new[1:3]:
                changes.append(
                    f"Clip {index + 1} source range: {old[1]:.3f}–{old[2]:.3f}s → "
                    f"{new[1]:.3f}–{new[2]:.3f}s."
                )
    for key, label in (
        ("visual_preset", "Framing"), ("transition", "Transitions"),
        ("include_source_audio", "Source audio"), ("crop", "Crop"),
    ):
        if [clip.get(key) for clip in previous.get("clips", [])] != [
            clip.get(key) for clip in current.get("clips", [])
        ]:
            changes.append(f"{label} changed.")
    for index, (old, new) in enumerate(zip(previous.get("clips", []), current.get("clips", []), strict=False)):
        old_gain = float(old.get("source_audio_gain_db") or 0)
        new_gain = float(new.get("source_audio_gain_db") or 0)
        if old_gain != new_gain:
            changes.append(f"Clip {index + 1} source volume: {old_gain:+g} → {new_gain:+g} dB.")
    for key, default, label in (
        ("music_track_id", None, "Music track"), ("music_mix", "none", "Music level"),
        ("effects", [], "Creative effects"), ("caption_position", "lower_safe", "Caption position"),
        ("caption_style", None, "Caption style"), ("audio_preset", None, "Audio processing"),
        ("end_card", "none", "End card"),
        ("broll", [], "B-roll overlays"), ("finishing", None, "Local finishing tools"),
        ("caption_timing_offset_seconds", 0, "Caption timing"),
    ):
        if previous.get(key, default) != current.get(key, default):
            changes.append(f"{label} changed.")
    before_tools, after_tools = previous.get("finishing") or {}, current.get("finishing") or {}
    for name, label in (("audio_regions", "Voice region"), ("caption_regions", "Caption region")):
        if before_tools.get(name, []) != after_tools.get(name, []):
            for region in after_tools.get(name, [])[:6]:
                value = f"{float(region.get('gain_db', 0)):+g} dB" if name == "audio_regions" else str(region.get("position", ""))
                changes.append(f"{label} {float(region['start']):.2f}–{float(region['end']):.2f}s: {value}.")
    return {
        "changed": bool(changes), "changes": changes,
        "source_selection_changed": before != after,
        "post_copy_changed": previous.get("post_copy", "") != current.get("post_copy", ""),
        "notice": "" if changes else (
            "This version keeps the same cut and render settings. Review the explanation below; "
            "choose Rebuild the story or name the phrase/moment to change."
        ),
        "editor_explanation": str(current.get("editorial_summary") or ""),
    }
