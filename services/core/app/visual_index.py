"""Source-derived keyframe extraction and local visual-embedding helpers."""

from __future__ import annotations

import json
import math
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, TypeVar

from app.config import Settings, get_settings
from app.media_analysis import resolve_source


VISUAL_MODEL_ID = "openai/clip-vit-base-patch32"
VISUAL_MODEL_REVISION = "c7244be81152024ce0e99ac8d2e373a8953d9f9a"
VISUAL_INDEX_VERSION = "1.1"
VISUAL_VECTOR_DIMENSION = 512
VISUAL_SAMPLE_INTERVAL_SECONDS = 1.5
VISUAL_MAX_FRAMES_PER_SCENE = 48
VISUAL_MAX_FRAMES_PER_ASSET = 120
VISUAL_MIN_SIMILARITY = 0.20
VISUAL_RELATIVE_SCORE_WINDOW = 0.07
VISUAL_MAX_SEARCH_RESULTS = 8


VisualMatch = TypeVar("VisualMatch")


def canonical_assignments(
    assets: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> dict[Any, Any]:
    """Resolve only current, complete exact-duplicate reviews to one record."""

    grouped: dict[str, list[Any]] = {}
    for asset in assets:
        grouped.setdefault(str(asset["sha256"]), []).append(asset["id"])
    reviewed = {str(review["sha256"]): review for review in reviews}
    assignments: dict[Any, Any] = {}
    for asset in assets:
        copies = grouped[str(asset["sha256"])]
        review = reviewed.get(str(asset["sha256"]))
        canonical_id = asset["id"]
        if (
            review is not None
            and int(review["asset_count"]) == len(copies)
            and review["canonical_asset_id"] in copies
        ):
            canonical_id = review["canonical_asset_id"]
        assignments[asset["id"]] = canonical_id
    return assignments


def representative_times(start: float, end: float) -> list[float]:
    """Sample a scene densely enough to catch brief visual subjects."""

    start = max(0.0, float(start))
    end = max(start, float(end))
    duration = end - start
    if duration <= 0:
        return [round(start, 3)]
    frame_count = min(
        VISUAL_MAX_FRAMES_PER_SCENE,
        max(1, math.ceil(duration / VISUAL_SAMPLE_INTERVAL_SECONDS)),
    )
    spacing = duration / frame_count
    return [round(start + spacing * (index + 0.5), 3) for index in range(frame_count)]


def evenly_limit(values: list[VisualMatch], maximum: int) -> list[VisualMatch]:
    """Keep temporal coverage when an unusually long asset exceeds its cap."""

    if maximum < 1:
        raise ValueError("maximum must be positive")
    if len(values) <= maximum:
        return values
    if maximum == 1:
        return [values[len(values) // 2]]
    indexes = [round(index * (len(values) - 1) / (maximum - 1)) for index in range(maximum)]
    return [values[index] for index in indexes]


def select_visual_matches(
    values: list[tuple[float, VisualMatch]],
    requested_limit: int,
) -> list[tuple[float, VisualMatch]]:
    """Discard weak long-tail CLIP matches while preserving ranked retrieval."""

    if requested_limit < 1 or not values:
        return []
    ordered = sorted(values, key=lambda item: item[0], reverse=True)
    strongest = ordered[0][0]
    if strongest < VISUAL_MIN_SIMILARITY:
        return []
    cutoff = max(VISUAL_MIN_SIMILARITY, strongest - VISUAL_RELATIVE_SCORE_WINDOW)
    maximum = min(requested_limit, VISUAL_MAX_SEARCH_RESULTS)
    return [item for item in ordered if item[0] >= cutoff][:maximum]


def normalized_dot(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values) or not left_values:
        raise ValueError("visual embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left_values, right_values)) / (left_norm * right_norm)


def _json_request(settings: Settings, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{settings.visual_encoder_url.rstrip('/')}/{path.lstrip('/')}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.visual_encoder_timeout_seconds) as response:
            decoded = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(1000).decode("utf-8", "replace")
        raise RuntimeError(f"visual encoder returned HTTP {error.code}: {detail}") from error
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"visual encoder is unavailable: {error}") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("visual encoder returned an invalid response")
    return decoded


def embed_text(text: str, settings: Settings | None = None) -> list[float]:
    settings = settings or get_settings()
    payload = _json_request(settings, "embed/text", {"text": " ".join(text.split())})
    embedding = payload.get("embedding")
    if not isinstance(embedding, list) or len(embedding) != VISUAL_VECTOR_DIMENSION:
        raise RuntimeError("visual encoder returned an invalid text embedding")
    return [float(value) for value in embedding]


def embed_frame_paths(paths: list[str], settings: Settings | None = None) -> list[list[float]]:
    settings = settings or get_settings()
    payload = _json_request(settings, "embed/images", {"paths": paths})
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(paths):
        raise RuntimeError("visual encoder returned an invalid image batch")
    normalized: list[list[float]] = []
    for embedding in embeddings:
        if not isinstance(embedding, list) or len(embedding) != VISUAL_VECTOR_DIMENSION:
            raise RuntimeError("visual encoder returned an invalid image embedding")
        normalized.append([float(value) for value in embedding])
    return normalized


def extract_visual_frame(
    source: Path,
    destination: Path,
    *,
    frame_seconds: float,
    is_image: bool,
    timeout: int,
) -> str:
    """Write a bounded JPEG derived from an immutable original."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.jpg")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if not is_image:
        command.extend(["-ss", f"{max(0.0, frame_seconds):.3f}"])
    command.extend(
        [
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=min(640\\,iw):-2",
            "-q:v",
            "3",
            str(temporary),
        ]
    )
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            detail = " | ".join(line.strip() for line in result.stderr.splitlines()[-6:] if line.strip())
            raise RuntimeError(f"visual keyframe extraction failed: {detail or 'no JPEG produced'}")
        os.replace(temporary, destination)
        destination.chmod(0o444)
    finally:
        temporary.unlink(missing_ok=True)
    return destination.as_posix()


def build_visual_frames(
    asset: dict[str, Any],
    segments: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    source = resolve_source(settings.media_root, str(asset["storage_key"]))
    is_image = str(asset.get("mime_type") or "").startswith("image/")
    directory = settings.media_root / "visual-index" / str(asset["project_id"]) / str(asset["id"])
    frames: list[dict[str, Any]] = []
    for segment in segments:
        kind = str(segment["segment_kind"])
        start = float(segment["start_seconds"])
        end = float(segment["end_seconds"])
        times = [0.0] if kind == "image" else representative_times(start, end)
        for frame_index, frame_seconds in enumerate(times):
            name = f"{kind}-{int(segment['segment_index']):04d}-{frame_index:02d}.jpg"
            destination = directory / name
            frames.append(
                {
                    "segment_kind": kind,
                    "segment_index": int(segment["segment_index"]),
                    "frame_index": frame_index,
                    "start_seconds": start,
                    "end_seconds": end,
                    "frame_seconds": frame_seconds,
                    "frame_path": destination.relative_to(settings.media_root).as_posix(),
                }
            )
    selected = evenly_limit(frames, VISUAL_MAX_FRAMES_PER_ASSET)
    # Bound decode and disk work, not just the number of vectors retained.
    for frame in selected:
        extract_visual_frame(source, settings.media_root / frame["frame_path"],
                            frame_seconds=frame["frame_seconds"], is_image=is_image,
                            timeout=settings.analysis_command_timeout_seconds)
    return selected
