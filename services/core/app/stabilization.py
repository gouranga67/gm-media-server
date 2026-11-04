"""Opt-in translation-shake reduction on a bounded set of main-picture clips.

No model, second analysis pass, source rewrite or timestamp change. FFmpeg's
deshake filter estimates motion while rendering; it cannot repair motion blur,
rolling shutter or distinguish every intentional pan from subject movement.
"""

VERSION = "translation_stabilization_v1"
MAX_CLIPS = 4
MAX_SECONDS = 8


def clip_choices(document):
    tools = document.get("finishing") or {}
    manual = {item["clip_index"] for item in tools.get("motions", [])}
    output = []
    for index, clip in enumerate(document.get("clips", [])):
        source_seconds = float(clip["source_out"] - clip["source_in"])
        duration = float(clip.get("duration", source_seconds))
        note = ""
        if clip.get("media_kind", "video") != "video":
            note = "Photos do not need camera-shake reduction."
        elif not 1 <= duration <= MAX_SECONDS:
            note = "Choose a 1–8 second shot; shorten longer shots first."
        elif abs(duration - source_seconds) > .001:
            note = "Retimed or held picture keeps its existing treatment."
        elif index in manual:
            note = "Manual camera anchors take priority; clear them first."
        output.append({"clip_index": index, "asset_id": str(clip["asset_id"]),
            "duration_seconds": round(duration, 3), "eligible": not bool(note), "note": note,
            "source_in": float(clip["source_in"]), "source_out": float(clip["source_out"])})
    return output


def validate_stabilization(plan):
    tools = plan.finishing
    if not tools or not tools.stabilize_clips:
        return
    indexes = tools.stabilize_clips
    if len(indexes) != len(set(indexes)):
        raise ValueError("select each stabilized clip only once")
    choices = {item["clip_index"]: item for item in clip_choices(plan.model_dump(mode="json"))}
    if any(index not in choices for index in indexes):
        raise ValueError("stabilization must identify existing clips")
    for index in indexes:
        if not choices[index]["eligible"]:
            raise ValueError(f"Clip {index + 1}: {choices[index]['note']}")
    if tools.smart_framing != "off":
        raise ValueError("turn off single-face follow before reducing camera shake")


def stabilization_filter(plan, index, width, height, fps):
    tools = plan.finishing
    if not tools or index not in tools.stabilize_clips:
        return ""
    # Defend direct renderer callers too, before FFmpeg starts. Its only motion
    # search is on the resized output, never a full-resolution camera original.
    validate_stabilization(plan)
    radius = 16 if min(width, height) < 1080 else 32
    crop_w, crop_h = int(width * .94) // 2 * 2, int(height * .94) // 2 * 2
    return (f"fps={fps},format=yuv420p,deshake=rx={radius}:ry={radius}:edge=mirror:search=less,"
        f"crop={crop_w}:{crop_h},scale={width}:{height},setsar=1")


def stabilization_manifest(plan):
    indexes = list(plan.finishing.stabilize_clips) if plan.finishing else []
    return {"version": VERSION, "clip_indexes": indexes, "max_clips": MAX_CLIPS,
        "max_clip_seconds": MAX_SECONDS, "edge_crop_fraction": .06, "hosted_model_calls": 0,
        "method": "ffmpeg_deshake", "quality_verified": False,
        "note": "Small translation-shake reduction with an approximately 6% edge crop. Review pans, moving subjects and edges; motion blur is not repaired."}
