"""Bounded visual coverage for mixed talking footage and picture cutaways."""

import base64
import io
from pathlib import Path
from typing import Any

from app.broll_evidence import speech_ranges
from app.media_analysis import resolve_source


def _candidate_order(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keep dialogue orientation, then alternate pictures and cutaway recordings.
    # Source order otherwise hides late-added product footage behind early takes.
    spoken, stills, videos = [], [], []
    for asset in assets:
        if str(asset.get("mime_type") or "").startswith("image/"):
            stills.append(asset)
        elif asset.get("has_video"):
            (spoken if speech_ranges(asset) else videos).append(asset)
    ordered = spoken[:1]
    for index in range(max(len(videos), len(stills))):
        if index < len(videos):
            ordered.append(videos[index])
        if index < len(stills):
            ordered.append(stills[index])
    return ordered + spoken[1:]


def high_impact_visuals(context: dict[str, Any], media_root: Path, image_limit: int = 4, *, pictured_asset_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Pack up to six sources per image, without increasing the image count.

    Worker Pillow is already pinned. Derivatives only; originals are not read or
    modified. A thumbnail is not evidence of every frame in a video range.
    """
    from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

    pictures = []
    for asset in _candidate_order(context.get("assets", [])):
        key = asset.get("_preview_key") or asset.get("_contact_sheet_key")
        if not isinstance(key, str):
            continue
        try:
            source = resolve_source(media_root, key)
            if source.stat().st_size > 3_000_000:
                continue
            with Image.open(source) as original:
                if original.width * original.height > 12_000_000:
                    continue
                picture = ImageOps.exif_transpose(original).convert("RGB")
                picture.thumbnail((640, 640))
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            continue
        pictures.append((asset, picture))
        if len(pictures) >= image_limit * 6:
            break
    if not pictures:
        return []
    # A small job keeps one useful, legible image per source. Larger selections
    # use balanced sheets so a late product shot does not disappear from view.
    per_sheet = min(6, (len(pictures) + image_limit - 1) // image_limit)
    content: list[dict[str, Any]] = []
    shown = {str(asset["asset_id"]) for asset, _ in pictures}
    if pictured_asset_ids is not None:
        pictured_asset_ids.update(shown)
    total_visual = sum(bool(asset.get("has_video")) or str(asset.get("mime_type") or "").startswith("image/")
                       for asset in context.get("assets", []))
    content.append({"type": "input_text", "text": (
        f"Visual coverage: {len(shown)} of {total_visual} visual sources pictured below. "
        "Source thumbnails only: they do not verify an entire source range, facial motion, or unreadable text. "
        "Do not claim to have inspected unpictured sources. Product/scene identity must be supported by a pictured panel or explicit source evidence."
    )})
    for offset in range(0, len(pictures), per_sheet):
        group = pictures[offset:offset + per_sheet]
        columns = 1 if len(group) == 1 else 2
        size = 512 if len(group) == 1 else 256
        rows = (len(group) + columns - 1) // columns
        sheet = Image.new("RGB", (size * columns, size * rows), "#e8edf0")
        draw = ImageDraw.Draw(sheet)
        mapping = []
        for index, (asset, picture) in enumerate(group):
            label = f"S{offset + index + 1}"
            cell = ImageOps.contain(picture, (size - 8, size - 28))
            x, y = (index % columns) * size, (index // columns) * size
            sheet.paste(cell, (x + (size - cell.width) // 2, y + 24 + (size - 28 - cell.height) // 2))
            draw.text((x + 8, y + 5), label, fill="#173f5f")
            mapping.append(f"{label}: asset {asset['asset_id']} ({str(asset.get('source_name') or '')[:160]})")
        encoded = io.BytesIO()
        sheet.save(encoded, format="JPEG", quality=82)
        content.extend([
            {"type": "input_text", "text": "Panel-to-source mapping: " + "; ".join(mapping)},
            {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii"), "detail": "low"},
        ])
    return content
