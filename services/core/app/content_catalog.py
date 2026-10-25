import json
from typing import Any

from app.config import Settings, get_settings
from app.media_analysis import resolve_source


CATALOG_VERSION = "1.2"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _transcript_segments(settings: Settings, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    key = manifest.get("derived", {}).get("transcript")
    if not isinstance(key, str):
        return []
    path = resolve_source(settings.media_root, key)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_segments = payload.get("segments")
    return raw_segments if isinstance(raw_segments, list) else []


def build_catalog_segments(
    asset: dict[str, Any],
    manifest: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Create searchable, source-derived facts without synthetic descriptions."""

    settings = settings or get_settings()
    source_name = str(asset.get("source_name") or "Untitled source")[:255]
    mime_type = str(asset.get("mime_type") or "application/octet-stream")
    probe = manifest.get("probe") if isinstance(manifest.get("probe"), dict) else {}
    probe_format = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    duration = _number(probe_format.get("duration_seconds"))
    segments: list[dict[str, Any]] = [
        {
            "segment_kind": "asset",
            "segment_index": 0,
            "start_seconds": 0.0,
            "end_seconds": duration,
            "text": source_name,
            "facts": {
                "mime_type": mime_type,
                "duration_seconds": duration,
                "sha256": asset.get("sha256"),
            },
            "source_model": "verified-ingest-metadata",
        }
    ]

    for index, raw in enumerate(_transcript_segments(settings, manifest)):
        if not isinstance(raw, dict):
            continue
        text = " ".join(str(raw.get("text") or "").split())
        start = _number(raw.get("start"))
        end = max(start, _number(raw.get("end"), start))
        if not text or end <= start:
            continue
        segments.append(
            {
                "segment_kind": "transcript",
                "segment_index": index,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": text[:4000],
                "facts": {"language": "source transcript"},
                "source_model": "faster-whisper-small",
            }
        )

    boundaries = manifest.get("derived", {}).get("scene_boundaries_seconds", [])
    clean_boundaries = sorted(
        {
            round(_number(value), 3)
            for value in boundaries
            if 0 < _number(value) < duration
        }
    ) if isinstance(boundaries, list) else []
    if mime_type.startswith("video/") and duration > 0:
        points = [0.0, *clean_boundaries, round(duration, 3)]
        for index, (start, end) in enumerate(zip(points, points[1:])):
            if end <= start:
                continue
            segments.append(
                {
                    "segment_kind": "scene",
                    "segment_index": index,
                    "start_seconds": start,
                    "end_seconds": end,
                    "text": f"Scene {index + 1} in {source_name}",
                    "facts": {"boundary_source": "ffmpeg scene detection"},
                    "source_model": "ffmpeg-scene-detect",
                }
            )
    elif mime_type.startswith("image/"):
        streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
        video_stream = next(
            (stream for stream in streams if isinstance(stream, dict) and stream.get("type") == "video"),
            {},
        )
        segments.append(
            {
                "segment_kind": "image",
                "segment_index": 0,
                "start_seconds": 0.0,
                "end_seconds": 0.0,
                "text": f"Still image {source_name}",
                "facts": {
                    "width": video_stream.get("width"),
                    "height": video_stream.get("height"),
                },
                "source_model": "ffprobe",
            }
        )
    return segments
