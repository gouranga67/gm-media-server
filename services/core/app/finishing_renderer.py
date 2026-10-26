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
        parts.append(
            f"[{source['input_index']}:v:0]{normalise}"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={cue.duration_seconds:.3f},"
            f"trim=duration={cue.duration_seconds:.3f},format=yuv420p,"
            f"setpts=PTS-STARTPTS+{cue.start_seconds:.3f}/TB[brollpicture{index}]"
        )
        end = cue.start_seconds + cue.duration_seconds
        parts.append(
            f"[brollbase{index}][brollpicture{index}]overlay=x=0:y=0:"
            f"enable='gte(t,{cue.start_seconds:.3f})*lt(t,{end:.3f})':"
            f"eof_action=pass:repeatlast=0[brollbase{index + 1}]"
        )
    parts.append(f"[brollbase{len(sources)}]{captions or 'null'}[vout]")
    return ";".join(parts)


def public_broll_manifest(context: dict[str, Any], plan: EditPlan) -> list[dict[str, Any]]:
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    return [{**cue.model_dump(mode="json"), "source_name": inventory[str(cue.asset_id)].get("source_name"),
             "sha256": inventory[str(cue.asset_id)].get("sha256"), "source_audio_used": False}
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
            "creative_effect_count": len(plan.effects), "dialogue_timeline_preserved": True,
            "additional_model_calls": 0}
