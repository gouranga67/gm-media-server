"""Typed job-level picture composition applied before optional treatments."""

from __future__ import annotations

import re
from typing import Any

from app.editor_context import (
    resolve_internal_asset_render_source,
    resolve_internal_asset_source,
)
from app.media_analysis import (
    hdr_to_sdr_filter,
    probe_media,
    still_image_input_arguments,
    video_probe_hdr_mode,
)


def selected_green_screen_background(
    context: dict[str, Any], settings: Any, input_index: int
) -> dict[str, Any] | None:
    composition = context.get("job", {}).get("composition") or {}
    if composition.get("mode") != "green_screen":
        return None
    background_id = str(composition.get("background_asset_id") or "")
    asset = next(
        (item for item in context.get("assets", []) if str(item.get("asset_id")) == background_id),
        None,
    )
    if asset is None:
        raise ValueError("the selected green-screen background is unavailable")
    media_kind = "image" if str(asset.get("mime_type") or "").startswith("image/") else "video"
    path = (
        resolve_internal_asset_source(settings, asset)
        if media_kind == "image"
        else resolve_internal_asset_render_source(settings, asset)
    )
    return {
        "asset_id": background_id,
        "input_index": input_index,
        "media_kind": media_kind,
        "path": path,
        "hdr_mode": (
            video_probe_hdr_mode(probe_media(path, settings.analysis_command_timeout_seconds))
            if media_kind == "video"
            else None
        ),
    }


def composition_background_inputs(
    background: dict[str, Any] | None, *, duration: float
) -> list[str]:
    if background is None:
        return []
    if background["media_kind"] == "image":
        return still_image_input_arguments(background["path"], duration=duration)
    return ["-stream_loop", "-1", "-i", str(background["path"])]


def append_green_screen_background(
    graph: str,
    background: dict[str, Any] | None,
    *,
    width: int,
    height: int,
    fps: int,
    duration: float,
    composition: dict[str, Any] | None = None,
) -> str:
    if background is None:
        return graph

    parts = graph.split(";")
    captions = None
    for index, part in enumerate(parts):
        match = re.fullmatch(r"\[([A-Za-z0-9_]+)\](subtitles=.*)\[vout\]", part)
        if match:
            captions = match[2]
            parts[index] = f"[{match[1]}]null[vout]"
            break
    parts = [part.replace("[vout]", "[compositionforeground]") for part in parts]

    normalise = (
        hdr_to_sdr_filter(background["hdr_mode"]) + ","
        if background.get("hdr_mode")
        else ""
    )
    parts.append(
        f"[{background['input_index']}:v:0]{normalise}"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[compositionbackground]"
    )
    settings = composition or {}
    key_color = str(settings.get("chroma_key_color") or "#00FF00")
    similarity = float(settings.get("chroma_similarity") or 0.12)
    blend = float(settings.get("chroma_blend") or 0.08)
    spill = float(settings.get("spill_suppression") or 0)
    key_filter = (
        "[compositionforeground]format=yuva444p,"
        f"chromakey=0x{key_color[1:]}:{similarity:.4f}:{blend:.4f}"
    )
    if spill > 0:
        spill_type = "blue" if key_color.upper() == "#0000FF" else "green"
        key_filter += f",despill=type={spill_type}:mix={spill:.4f}"
    parts.append(key_filter + ",format=rgba[compositionkeyed]")
    parts.append(
        "[compositionbackground][compositionkeyed]"
        "overlay=x=0:y=0:eof_action=pass:repeatlast=1[compositionbase]"
    )
    parts.append(f"[compositionbase]{captions or 'null'}[vout]")
    return ";".join(parts)
