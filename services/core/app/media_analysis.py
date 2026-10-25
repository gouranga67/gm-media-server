import json
import math
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings


READ_ONLY_MODE = 0o440
SCENE_TIMESTAMP_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
LOUDNESS_JSON_PATTERN = re.compile(r"\{\s*\"input_i\".*?\}", re.DOTALL)
EDGE_ENERGY_PATTERN = re.compile(r"lavfi\.signalstats\.YAVG=([0-9]+(?:\.[0-9]+)?)")


def resolve_source(media_root: Path, storage_key: str) -> Path:
    """Resolve a database storage key without permitting path traversal or symlinks."""

    if not storage_key or Path(storage_key).is_absolute() or "\\" in storage_key:
        raise ValueError("invalid asset storage key")
    candidate = media_root.joinpath(*Path(storage_key).parts)
    resolved_root = media_root.resolve()
    lexical_target = candidate.resolve(strict=False)
    if not lexical_target.is_relative_to(resolved_root):
        raise ValueError("asset source is outside the media root")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ValueError("asset source is outside the media root")
    return resolved


def ensure_capacity(settings: "Settings") -> dict[str, int | float]:
    usage = shutil.disk_usage(settings.media_root)
    free_percent = usage.free / usage.total * 100
    if usage.free < settings.media_min_free_bytes:
        raise RuntimeError("media processing paused: free space is below the byte safety floor")
    if free_percent < settings.media_min_free_percent:
        raise RuntimeError("media processing paused: free space is below the percentage safety floor")
    return {"free_bytes": usage.free, "free_percent": round(free_percent, 2)}


def run_command(
    arguments: Sequence[str],
    *,
    timeout: int,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["unknown command failure"]
        raise RuntimeError(f"media command failed: {detail[0][:300]}")
    return completed


def _number(value: Any, converter: type[int] | type[float]) -> int | float | None:
    try:
        return converter(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _frame_rate(value: Any) -> float | None:
    if not isinstance(value, str) or value in {"", "0/0"}:
        return None
    try:
        result = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return round(result, 3) if math.isfinite(result) else None


def normalize_probe(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only technical fields; embedded titles, comments, and location tags are excluded."""

    streams: list[dict[str, Any]] = []
    for raw_stream in payload.get("streams", []):
        stream_type = raw_stream.get("codec_type")
        if stream_type not in {"video", "audio"}:
            continue
        stream: dict[str, Any] = {
            "index": _number(raw_stream.get("index"), int),
            "type": stream_type,
            "codec": raw_stream.get("codec_name"),
            "duration_seconds": _number(raw_stream.get("duration"), float),
        }
        if stream_type == "video":
            rotation: int | None = None
            side_data = raw_stream.get("side_data_list", [])
            if isinstance(side_data, list):
                for item in side_data:
                    if isinstance(item, dict) and item.get("rotation") is not None:
                        rotation = _number(item.get("rotation"), int)  # type: ignore[assignment]
                        break
            if rotation is None and isinstance(raw_stream.get("tags"), dict):
                rotation = _number(raw_stream["tags"].get("rotate"), int)  # type: ignore[assignment]
            stream.update(
                {
                    "width": _number(raw_stream.get("width"), int),
                    "height": _number(raw_stream.get("height"), int),
                    "frames_per_second": _frame_rate(raw_stream.get("r_frame_rate")),
                    "rotation_degrees": rotation,
                    "pixel_format": raw_stream.get("pix_fmt"),
                    "color_range": raw_stream.get("color_range"),
                    "color_space": raw_stream.get("color_space"),
                    "color_transfer": raw_stream.get("color_transfer"),
                    "color_primaries": raw_stream.get("color_primaries"),
                }
            )
        else:
            stream.update(
                {
                    "sample_rate_hz": _number(raw_stream.get("sample_rate"), int),
                    "channels": _number(raw_stream.get("channels"), int),
                    "channel_layout": raw_stream.get("channel_layout"),
                }
            )
        streams.append({key: value for key, value in stream.items() if value is not None})

    raw_format = payload.get("format", {})
    format_facts = {
        "container": raw_format.get("format_name"),
        "duration_seconds": _number(raw_format.get("duration"), float),
        "size_bytes": _number(raw_format.get("size"), int),
        "bit_rate": _number(raw_format.get("bit_rate"), int),
    }
    return {
        "format": {key: value for key, value in format_facts.items() if value is not None},
        "streams": streams,
    }


def probe_media(source: Path, timeout: int) -> dict[str, Any]:
    completed = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ],
        timeout=timeout,
    )
    return normalize_probe(json.loads(completed.stdout))


def video_probe_is_hdr(probe: dict[str, Any]) -> bool:
    """Identify common HDR10 and HLG video signals from normalized ffprobe data."""

    video = next(
        (stream for stream in probe.get("streams", []) if stream.get("type") == "video"),
        {},
    )
    transfer = str(video.get("color_transfer") or "").lower()
    primaries = str(video.get("color_primaries") or "").lower()
    pixel_format = str(video.get("pixel_format") or "").lower()
    return (
        transfer in {"smpte2084", "arib-std-b67"}
        or primaries in {"bt2020", "bt2020nc", "bt2020ncl"}
        or ("10" in pixel_format and transfer not in {"", "bt709"})
    )


def hdr_to_sdr_filter() -> str:
    """Return a conservative BT.2020 HDR/HLG to BT.709 SDR tone-map chain."""

    return (
        "zscale=t=linear:npl=100,format=gbrpf32le,"
        "tonemap=mobius:desat=1,"
        "zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p"
    )


def _install_generated(temporary: Path, destination: Path) -> None:
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError(f"media command did not create {destination.name}")
    temporary.chmod(READ_ONLY_MODE)
    os.replace(temporary, destination)
    directory_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def generate_file(arguments: Sequence[str], destination: Path, timeout: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.part{destination.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        run_command([*arguments, str(temporary)], timeout=timeout)
        _install_generated(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _relative(media_root: Path, path: Path) -> str:
    return path.relative_to(media_root).as_posix()


def _has_stream(probe: dict[str, Any], stream_type: str) -> bool:
    return any(stream.get("type") == stream_type for stream in probe["streams"])


def create_video_proxy(source: Path, destination: Path, timeout: int) -> str:
    source_probe = probe_media(source, timeout)
    video_filter = "scale='min(1920,iw)':-2"
    if video_probe_is_hdr(source_probe):
        video_filter = f"{hdr_to_sdr_filter()},{video_filter}"
    common = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        # This proxy is also the deterministic render mezzanine. Preserve up
        # to 1080p landscape instead of reducing future exports to 720p.
        video_filter,
    ]
    nvenc = [
        *common,
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p4",
        "-cq",
        "25",
        "-b:v",
        "0",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-movflags",
        "+faststart",
    ]
    try:
        generate_file(nvenc, destination, timeout)
        return "h264_nvenc"
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"NVENC unavailable for proxy; using CPU fallback: {error}", flush=True)

    software = [
        *common,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "25",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-movflags",
        "+faststart",
    ]
    generate_file(software, destination, timeout)
    return "libx264"


def create_image(source: Path, destination: Path, width: int, timeout: int) -> None:
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({width},iw)':-2",
            "-q:v",
            "3",
        ],
        destination,
        timeout,
    )


def create_video_thumbnails(
    source: Path,
    thumbnail: Path,
    contact_sheet: Path,
    duration: float,
    timeout: int,
) -> None:
    seek = min(5.0, max(0.0, duration * 0.1))
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{seek:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale='min(640,iw)':-2",
            "-q:v",
            "3",
        ],
        thumbnail,
        timeout,
    )
    interval = max(duration / 9.0, 0.25)
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            f"fps=1/{interval:.6f},scale=320:-2,tile=3x3:padding=4:margin=4",
            "-q:v",
            "4",
        ],
        contact_sheet,
        timeout,
    )


def detect_scenes(source: Path, timeout: int) -> list[float]:
    completed = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-vf",
            "select='gt(scene,0.30)',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        timeout=timeout,
    )
    return sorted({round(float(match), 3) for match in SCENE_TIMESTAMP_PATTERN.findall(completed.stderr)})


def measure_visual_quality(source: Path, duration: float, timeout: int) -> dict[str, Any]:
    """Estimate sharpness from sampled edge energy without retaining extra frames."""

    interval = max(duration / 9.0, 0.25)
    completed = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-frames:v",
            "9",
            "-vf",
            (
                f"fps=1/{interval:.6f},scale=320:-2,format=gray,"
                "edgedetect=low=0.1:high=0.4,signalstats,metadata=print:file=-"
            ),
            "-an",
            "-f",
            "null",
            "-",
        ],
        timeout=timeout,
        check=False,
    )
    samples = [round(float(value), 3) for value in EDGE_ENERGY_PATTERN.findall(completed.stdout)]
    if not samples:
        return {"status": "unavailable", "method": "edge-energy-v1"}
    return {
        "status": "measured",
        "method": "edge-energy-v1",
        "sample_count": len(samples),
        "mean_sharpness_score": round(sum(samples) / len(samples), 3),
        "minimum_sharpness_score": min(samples),
    }


def measure_loudness(source: Path, timeout: int) -> dict[str, float | str]:
    completed = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-vn",
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=timeout,
    )
    matches = LOUDNESS_JSON_PATTERN.findall(completed.stderr)
    if not matches:
        return {"status": "unavailable"}
    raw = json.loads(matches[-1])
    result: dict[str, float | str] = {"status": "measured"}
    for output_name, input_name in {
        "integrated_lufs": "input_i",
        "true_peak_dbfs": "input_tp",
        "loudness_range_lu": "input_lra",
        "threshold_lufs": "input_thresh",
    }.items():
        value = _number(raw.get(input_name), float)
        if value is not None:
            result[output_name] = value
    return result


def create_audio_proxy(source: Path, destination: Path, timeout: int) -> None:
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
        ],
        destination,
        timeout,
    )


def create_waveform(source: Path, destination: Path, timeout: int) -> None:
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            "aformat=channel_layouts=mono,showwavespic=s=1200x240:colors=0x1f5f8b",
            "-frames:v",
            "1",
        ],
        destination,
        timeout,
    )


def format_vtt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def render_webvtt(segments: list[dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        lines.extend(
            [
                str(index),
                f"{format_vtt_timestamp(float(segment['start']))} --> "
                f"{format_vtt_timestamp(float(segment['end']))}",
                text,
                "",
            ]
        )
    return "\n".join(lines)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(READ_ONLY_MODE)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def transcribe(source: Path, settings: "Settings") -> tuple[dict[str, Any], str]:
    from faster_whisper import WhisperModel

    model_path = str(settings.transcription_model_path)
    attempts = (
        [("cuda", "int8_float16"), ("cpu", "int8")]
        if settings.transcription_device == "auto"
        else [(settings.transcription_device, "int8_float16" if settings.transcription_device == "cuda" else "int8")]
    )
    last_error: Exception | None = None
    for device, compute_type in attempts:
        try:
            model = WhisperModel(model_path, device=device, compute_type=compute_type, local_files_only=True)
            raw_segments, info = model.transcribe(
                str(source),
                beam_size=5,
                vad_filter=True,
                word_timestamps=True,
            )
            segments: list[dict[str, Any]] = []
            for raw in raw_segments:
                words = [
                    {
                        "start": word.start,
                        "end": word.end,
                        "text": word.word,
                        "probability": round(word.probability, 4),
                    }
                    for word in (raw.words or [])
                ]
                segments.append(
                    {
                        "start": round(raw.start, 3),
                        "end": round(raw.end, 3),
                        "text": raw.text.strip(),
                        "words": words,
                    }
                )
            transcript = {
                "engine": "faster-whisper",
                "model": "small",
                "device": device,
                "language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration_seconds": round(info.duration, 3),
                "segments": segments,
            }
            return transcript, render_webvtt(segments)
        except Exception as error:
            last_error = error
            if device != "cuda" or len(attempts) == 1:
                raise
            print(f"CUDA transcription unavailable; using CPU fallback: {error}", flush=True)
    assert last_error is not None
    raise last_error


def analyze_asset(
    asset: dict[str, Any], settings: "Settings | None" = None
) -> dict[str, Any]:
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    capacity = ensure_capacity(settings)
    source = resolve_source(settings.media_root, str(asset["storage_key"]))
    project_id = str(asset["project_id"])
    asset_id = str(asset["id"])
    timeout = settings.analysis_command_timeout_seconds
    probe = probe_media(source, timeout)
    has_video = _has_stream(probe, "video")
    has_audio = _has_stream(probe, "audio")
    duration = float(probe["format"].get("duration_seconds", 0.0))
    is_image = str(asset.get("mime_type", "")).startswith("image/")

    proxy_directory = settings.media_root / "proxies" / project_id / asset_id
    preview_directory = settings.media_root / "previews" / project_id / asset_id
    analysis_directory = settings.media_root / "analysis" / project_id / asset_id
    derived: dict[str, Any] = {}

    if has_video and not is_image:
        proxy = proxy_directory / "proxy.mp4"
        encoder = create_video_proxy(source, proxy, timeout)
        thumbnail = preview_directory / "thumbnail.jpg"
        contact_sheet = preview_directory / "contact-sheet.jpg"
        create_video_thumbnails(source, thumbnail, contact_sheet, duration, timeout)
        derived.update(
            {
                "proxy": _relative(settings.media_root, proxy),
                "proxy_encoder": encoder,
                "thumbnail": _relative(settings.media_root, thumbnail),
                "contact_sheet": _relative(settings.media_root, contact_sheet),
                "scene_boundaries_seconds": detect_scenes(source, timeout),
                "visual_quality": measure_visual_quality(source, duration, timeout),
            }
        )
    if is_image:
        preview = preview_directory / "preview.jpg"
        thumbnail = preview_directory / "thumbnail.jpg"
        create_image(source, preview, 1600, timeout)
        create_image(source, thumbnail, 480, timeout)
        derived = {
            "preview": _relative(settings.media_root, preview),
            "thumbnail": _relative(settings.media_root, thumbnail),
            "visual_quality": measure_visual_quality(source, duration, timeout),
        }

    if has_audio:
        derived["loudness"] = measure_loudness(source, timeout)
        if not has_video:
            audio_proxy = proxy_directory / "proxy.m4a"
            waveform = preview_directory / "waveform.png"
            create_audio_proxy(source, audio_proxy, timeout)
            create_waveform(source, waveform, timeout)
            derived["proxy"] = _relative(settings.media_root, audio_proxy)
            derived["waveform"] = _relative(settings.media_root, waveform)

        transcript, webvtt = transcribe(source, settings)
        transcript_path = analysis_directory / "transcript.json"
        captions_path = analysis_directory / "captions.vtt"
        atomic_write(transcript_path, json.dumps(transcript, indent=2, ensure_ascii=False) + "\n")
        atomic_write(captions_path, webvtt)
        derived["transcript"] = _relative(settings.media_root, transcript_path)
        derived["captions"] = _relative(settings.media_root, captions_path)

    manifest = {
        "schema_version": "1.0",
        "asset_id": asset_id,
        "project_id": project_id,
        "source": {
            "storage_key": str(asset["storage_key"]),
            "mime_type": asset.get("mime_type"),
            "byte_size": asset.get("byte_size"),
            "sha256": asset.get("sha256"),
        },
        "probe": probe,
        "derived": derived,
        "capacity_at_start": capacity,
        "content_policy": {"source_derived_only": True, "synthetic_media": False},
    }
    manifest_path = analysis_directory / "manifest.json"
    manifest["manifest_path"] = _relative(settings.media_root, manifest_path)
    atomic_write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest
