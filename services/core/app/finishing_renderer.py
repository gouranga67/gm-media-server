"""Picture-only finishing layers: the base dialogue timeline never changes."""

import re
from typing import Any

from app.config import Settings
from app.edit_plan import EditPlan
from app.editor_context import resolve_internal_asset_render_source, resolve_internal_asset_source
from app.media_analysis import hdr_to_sdr_filter, probe_media, video_probe_hdr_mode


def rhythmic_zoom(frames_per_second: int) -> str:
    beat = round(2.5 * frames_per_second)
    return f"if(lt(mod(on,{beat * 2}),{beat}),1,1.12)"


def selected_broll(context: dict[str, Any], plan: EditPlan, settings: Settings, first_input_index: int) -> list[dict[str, Any]]:
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    selected = []
    for index, cue in enumerate(plan.broll):
        asset = inventory[str(cue.asset_id)]
        source = resolve_internal_asset_source(settings, asset) if cue.media_kind == "image" else resolve_internal_asset_render_source(settings, asset)
        selected.append({"cue": cue, "path": source, "input_index": first_input_index + index,
                         "source_name": asset.get("source_name"), "sha256": asset.get("sha256"),
                         "caption_position": plan.caption_position,
                         "hdr_mode": video_probe_hdr_mode(probe_media(source, settings.analysis_command_timeout_seconds))
                         if cue.media_kind == "video" else None})
    return selected


def broll_input_arguments(sources: list[dict[str, Any]]) -> list[str]:
    arguments = []
    for source in sources:
        cue = source["cue"]
        if cue.media_kind == "image":
            arguments += ["-loop", "1", "-t", f"{cue.duration_seconds:.3f}", "-i", str(source["path"])]
        else:
            arguments += ["-ss", f"{cue.source_in:.3f}", "-t", f"{cue.duration_seconds:.3f}", "-i", str(source["path"])]
    return arguments


def image_broll_layout(width: int, height: int, caption_position: str = "lower_safe") -> dict[str, int]:
    """A contained still card clear of the chosen caption band, in square pixels."""
    vertical = height > width
    height_ratio, center_y = (0.48, 0.36) if vertical else (0.62, 0.38)
    if caption_position == "upper":
        height_ratio, center_y = (0.40, 0.53) if vertical else (0.50, 0.62)
    elif caption_position == "middle":
        height_ratio, center_y = 0.30, 0.25
    # Even bounds keep chroma subsampling stable at preview and export sizes.
    return {
        "max_width": max(2, int(width * 0.90) // 2 * 2),
        "max_height": max(2, int(height * height_ratio) // 2 * 2),
        "center_y": round(height * center_y),
    }


def append_broll_filters(graph: str, sources: list[dict[str, Any]], *, width: int, height: int, fps: int) -> str:
    if not sources:
        return graph
    parts = graph.split(";")
    captions = None
    for index, part in enumerate(parts):
        match = re.fullmatch(r"\[([A-Za-z0-9_]+)\](subtitles=.*)\[vout\]", part)
        if match:
            captions = match[2]
            parts[index] = f"[{match[1]}]null[vout]"
            break
    # Rename the existing video sink once. Audio labels/filters are untouched.
    parts = [part.replace("[vout]", "[brollbase0]") for part in parts]
    for index, source in enumerate(sources):
        cue = source["cue"]
        normalise = hdr_to_sdr_filter(source["hdr_mode"]) + "," if source.get("hdr_mode") else ""
        end = cue.start_seconds + cue.duration_seconds
        active = f"gte(t,{cue.start_seconds:.3f})*lt(t,{end:.3f})"
        if cue.media_kind == "image":
            layout = image_broll_layout(width, height, source.get("caption_position", "lower_safe"))
            # A review, screenshot or still must retain all four edges. Do not
            # inherit a video's center-fill crop or flatten PNG alpha to YUV.
            sizing = (
                f"scale={layout['max_width']}:{layout['max_height']}:"
                "force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "setsar=1,format=rgba,"
            )
            base = f"brollbackdrop{index}"
            parts.append(
                f"[brollbase{index}]drawbox=x=0:y=0:w=iw:h=ih:"
                f"color=black@0.55:t=fill:enable='{active}'[{base}]"
            )
            position = f"x=(W-w)/2:y={layout['center_y']}-h/2"
        else:
            sizing = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,format=yuv420p,"
            )
            base = f"brollbase{index}"
            position = "x=0:y=0"
        parts.append(
            f"[{source['input_index']}:v:0]{normalise}{sizing}"
            f"fps={fps},tpad=stop_mode=clone:stop_duration={cue.duration_seconds:.3f},"
            f"trim=duration={cue.duration_seconds:.3f},"
            f"setpts=PTS-STARTPTS+{cue.start_seconds:.3f}/TB[brollpicture{index}]"
        )
        parts.append(
            f"[{base}][brollpicture{index}]overlay={position}:"
            f"enable='{active}':"
            f"eof_action=pass:repeatlast=0[brollbase{index + 1}]"
        )
    parts.append(f"[brollbase{len(sources)}]{captions or 'null'}[vout]")
    return ";".join(parts)


def public_broll_manifest(context: dict[str, Any], plan: EditPlan) -> list[dict[str, Any]]:
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    return [{**cue.model_dump(mode="json"), "source_name": inventory[str(cue.asset_id)].get("source_name"),
             "sha256": inventory[str(cue.asset_id)].get("sha256"), "source_audio_used": False,
             "framing": "contain_card_v1" if cue.media_kind == "image" else "center_fill",
             "source_cropped": cue.media_kind != "image",
             "alpha_preserved": cue.media_kind == "image",
             "caption_position": plan.caption_position}
            for cue in plan.broll]


def finishing_manifest(context: dict[str, Any], plan: EditPlan) -> dict[str, Any]:
    from app.edit_plan import MontageEditPlan

    beats = []
    timeline = 0.0
    for clip in plan.clips:
        duration = float(clip.duration) if isinstance(plan, MontageEditPlan) else float(clip.source_out - clip.source_in)
        if clip.visual_preset == "rhythmic_punch":
            at = 2.5
            while at < duration - 0.05:
                beats.append(round(timeline + at, 3))
                at += 2.5
        timeline += duration
    return {"mode": context["job"].get("edit_style"), "target_visual_beat_seconds": 2.5,
            "rhythmic_punch_beats": beats, "broll_count": len(plan.broll),
            "image_broll_framing": "contain_card_v1",
            "creative_effect_count": len(plan.effects), "dialogue_timeline_preserved": True,
            "broll_selection_review": context.get("broll_selection_review", []),
            "additional_model_calls": 0}
