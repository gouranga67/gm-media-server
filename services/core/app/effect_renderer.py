from pathlib import Path
import re
from typing import Any

from app.config import Settings
from app.edit_plan import EditPlan
from app.media_analysis import resolve_source


AUDIO_KINDS = {"sound_effect", "meme_sound"}
VISUAL_KINDS = {"sticker", "gif", "meme_image"}


def selected_effects(
    context: dict[str, Any], plan: EditPlan, settings: Settings, first_input_index: int
) -> list[dict[str, Any]]:
    inventory = {
        str(item["asset_id"]): item for item in context.get("creative_effect_library", [])
    }
    selected: list[dict[str, Any]] = []
    for offset, cue in enumerate(plan.effects):
        item = inventory.get(str(cue.asset_id))
        if item is None or not isinstance(item.get("_storage_key"), str):
            raise RuntimeError("an approved creative effect is unavailable to the renderer")
        selected.append(
            {
                **{key: value for key, value in item.items() if not key.startswith("_")},
                "cue": cue,
                "input_index": first_input_index + offset,
                "path": resolve_source(settings.media_root, item["_storage_key"]),
            }
        )
    return selected


def effect_input_arguments(effects: list[dict[str, Any]]) -> list[str]:
    arguments: list[str] = []
    for effect in effects:
        kind = effect["kind"]
        path = Path(effect["path"])
        if kind == "gif":
            arguments.extend(["-stream_loop", "-1", "-i", str(path)])
        elif kind in {"sticker", "meme_image"}:
            arguments.extend(["-loop", "1", "-i", str(path)])
        else:
            arguments.extend(["-i", str(path)])
    return arguments


def append_effect_filters(
    graph: str,
    effects: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    total_duration: float,
) -> str:
    if not effects:
        return graph
    visual = [item for item in effects if item["kind"] in VISUAL_KINDS]
    audio = [item for item in effects if item["kind"] in AUDIO_KINDS]
    graph_parts = graph.split(";")
    caption_filter: str | None = None
    caption_input: str | None = None
    for index, part in enumerate(graph_parts):
        match = re.fullmatch(r"\[([A-Za-z0-9_]+)\](subtitles=.*)\[vout\]", part)
        if match is not None:
            caption_input, caption_filter = match.groups()
            graph_parts.pop(index)
            graph_parts.append(f"[{caption_input}]null[vout]")
            break
    filters = [";".join(graph_parts).replace("[vout]", "[vfx0]").replace("[aout]", "[afx0]")]
    final_video_label = "veffects" if caption_filter is not None else "vout"

    current_video = "vfx0"
    for index, item in enumerate(visual, start=1):
        cue = item["cue"]
        scale_ratio = {"subtle": 0.20, "standard": 0.28, "strong": 0.38}[cue.intensity]
        if cue.position == "full_frame":
            scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
            x, y = "(W-w)/2", "(H-h)/2"
        else:
            scale = f"scale={max(96, round(width * scale_ratio))}:-1"
            x = "(W-w)/2"
            y = {"top": "H*0.12", "center": "(H-h)/2", "bottom": "H-h-H*0.24"}[cue.position]
        effect_label = f"vasset{index}"
        output_label = final_video_label if index == len(visual) else f"vfx{index}"
        start = float(cue.start_seconds)
        end = start + float(cue.duration_seconds)
        filters.append(
            f"[{item['input_index']}:v:0]{scale},format=rgba,setpts=PTS-STARTPTS+{start:.3f}/TB[{effect_label}]"
        )
        filters.append(
            f"[{current_video}][{effect_label}]overlay=x='{x}':y='{y}':"
            f"enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[{output_label}]"
        )
        current_video = output_label
    if not visual:
        filters.append(f"[vfx0]null[{final_video_label}]")
    if caption_filter is not None:
        filters.append(f"[{final_video_label}]{caption_filter}[vout]")

    audio_labels: list[str] = []
    for index, item in enumerate(audio, start=1):
        cue = item["cue"]
        duration = float(cue.duration_seconds)
        start_ms = max(0, round(float(cue.start_seconds) * 1000))
        gain = {"subtle": -12.0, "standard": -8.0, "strong": -4.0}[cue.intensity]
        label = f"sfx{index}"
        fade = min(0.05, duration / 5)
        filters.append(
            f"[{item['input_index']}:a:0]aresample=48000,atrim=0:{duration:.3f},"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={max(0.0, duration-fade):.3f}:d={fade:.3f},"
            f"volume={gain:.1f}dB,adelay={start_ms}|{start_ms},"
            f"apad=pad_dur={total_duration:.3f},atrim=0:{total_duration:.3f}[{label}]"
        )
        audio_labels.append(f"[{label}]")
    if audio_labels:
        filters.append(
            "[afx0]" + "".join(audio_labels)
            + f"amix=inputs={len(audio_labels)+1}:duration=first:dropout_transition=0:normalize=0,"
              "alimiter=limit=0.95[aout]"
        )
    else:
        filters.append("[afx0]anull[aout]")
    return ";".join(filters)


def public_effect_manifest(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset_id": str(item["asset_id"]),
            "kind": item["kind"],
            "title": item["title"],
            "purpose": item["purpose"],
            "license_name": item["license_name"],
            "license_source_url": item["license_source_url"],
            "attribution": item.get("attribution") or "",
            "start_seconds": item["cue"].start_seconds,
            "duration_seconds": item["cue"].duration_seconds,
            "position": item["cue"].position,
            "intensity": item["cue"].intensity,
        }
        for item in effects
    ]
