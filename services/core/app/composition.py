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


def selected_composition_background(
    context: dict[str, Any], settings: Any, input_index: int,
    *, cutout_matte_path: Any | None = None,
) -> dict[str, Any] | None:
    composition = context.get("job", {}).get("composition") or {}
    mode = composition.get("mode")
    if mode == "person_cutout" and not composition.get("person_cutout_enabled"):
        return None
    if mode not in {"green_screen", "person_cutout"}:
        return None
    if mode == "person_cutout" and cutout_matte_path is None:
        raise ValueError("full-reel background replacement needs a prepared person matte")
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
        "kind": mode,
        "asset_id": background_id,
        "input_index": input_index,
        "matte_input_index": input_index + 1 if mode == "person_cutout" else None,
        "matte_path": cutout_matte_path,
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
        result = still_image_input_arguments(background["path"], duration=duration)
    else:
        result = ["-stream_loop", "-1", "-i", str(background["path"])]
    if background.get("kind") == "person_cutout":
        result.extend(["-i", str(background["matte_path"])])
    return result


def composition_input_count(background: dict[str, Any] | None) -> int:
    if background is None:
        return 0
    return 2 if background.get("kind") == "person_cutout" else 1


def append_composition_background(
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
    if background.get("kind") == "person_cutout":
        parts.append(
            f"[{background['matte_input_index']}:v:0]"
            f"scale={width}:{height},fps={fps},trim=duration={duration:.3f},"
            "setpts=PTS-STARTPTS,format=gray[compositionalpha]"
        )
        parts.append(
            "[compositionforeground]format=rgb24[compositioncolour]"
        )
        parts.append(
            "[compositioncolour][compositionalpha]alphamerge[compositionkeyed]"
        )
    else:
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


# Compatibility names for the existing chroma-key contract and tests.
selected_green_screen_background = selected_composition_background
append_green_screen_background = append_composition_background
