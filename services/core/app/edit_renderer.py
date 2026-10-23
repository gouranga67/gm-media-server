import json
import os
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.edit_plan import TalkingHeadEditPlan, document_sha256
from app.editor_context import resolve_internal_asset_source
from app.media_analysis import READ_ONLY_MODE, ensure_capacity, run_command


PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
PREVIEW_FPS = 30


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def _ass_text(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", " ")
        .replace("\n", r"\N")
        .strip()
    )


def caption_events(
    plan: TalkingHeadEditPlan, assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map source transcript time to the assembled preview timeline."""

    inventory = {str(asset["asset_id"]): asset for asset in assets}
    events: list[dict[str, Any]] = []
    timeline_start = 0.0
    for clip in plan.clips:
        source_in = float(clip.source_in)
        source_out = float(clip.source_out)
        asset = inventory[str(clip.asset_id)]
        for segment in asset.get("transcript_segments", []):
            try:
                segment_start = float(segment["start"])
                segment_end = float(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            visible_start = max(segment_start, source_in)
            visible_end = min(segment_end, source_out)
            text = str(segment.get("text", "")).strip()
            if visible_end - visible_start < 0.08 or not text:
                continue
            events.append(
                {
                    "start": timeline_start + visible_start - source_in,
                    "end": timeline_start + visible_end - source_in,
                    "text": text,
                }
            )
        timeline_start += source_out - source_in
    return events


def render_ass(events: list[dict[str, Any]]) -> str:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 540
PlayResY: 960
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: GMBlue,Arial,34,&H00FFFFFF,&H00FFFFFF,&H00B45B19,&H78000000,-1,0,0,0,100,100,0,0,1,3,1,2,38,38,86,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for event in events:
        lines.append(
            "Dialogue: 0,"
            f"{_ass_timestamp(float(event['start']))},{_ass_timestamp(float(event['end']))},"
            f"GMBlue,,0,0,0,,{_ass_text(str(event['text']))}\n"
        )
    return "".join(lines)


def _atomic_text(path: Path, content: str) -> None:
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
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _ffmpeg_filter(clip_count: int, captions_path: Path) -> str:
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index in range(clip_count):
        filters.append(
            f"[{index}:v:0]scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:"
            "force_original_aspect_ratio=increase,"
            f"crop={PREVIEW_WIDTH}:{PREVIEW_HEIGHT},setsar=1,fps={PREVIEW_FPS}[v{index}]"
        )
        filters.append(
            f"[{index}:a:0]aresample=48000,asetpts=PTS-STARTPTS[a{index}]"
        )
        concat_inputs.extend((f"[v{index}]", f"[a{index}]"))
    filters.append(
        "".join(concat_inputs) + f"concat=n={clip_count}:v=1:a=1[vcat][acat]"
    )
    safe_caption_path = str(captions_path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
    filters.append(f"[vcat]subtitles=filename='{safe_caption_path}'[vout]")
    filters.append("[acat]loudnorm=I=-16:LRA=11:TP=-1.5[aout]")
    return ";".join(filters)


def _render_video(
    sources: list[tuple[Path, float, float]],
    captions_path: Path,
    destination: Path,
    timeout: int,
) -> str:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for source, source_in, source_out in sources:
        common.extend(
            ["-ss", f"{source_in:.3f}", "-t", f"{source_out - source_in:.3f}", "-i", str(source)]
        )
    common.extend(
        [
            "-filter_complex",
            _ffmpeg_filter(len(sources), captions_path),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
        ]
    )
    encoders = (
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24", "-b:v", "0"]),
        ("libx264", ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.part{destination.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        for encoder, arguments in encoders:
            temporary.unlink(missing_ok=True)
            command = [
                *common,
                *arguments,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(temporary),
            ]
            completed = run_command(command, timeout=timeout, check=False)
            if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                temporary.chmod(READ_ONLY_MODE)
                os.replace(temporary, destination)
                return encoder
            if encoder == "h264_nvenc":
                print("NVENC preview render unavailable; using libx264 fallback", flush=True)
        raise RuntimeError("preview render failed with both NVENC and libx264")
    finally:
        temporary.unlink(missing_ok=True)


def render_edit_preview(
    context: dict[str, Any],
    plan: TalkingHeadEditPlan,
    version: int,
    provider: str,
    model: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    capacity = ensure_capacity(settings)
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    sources = [
        (
            resolve_internal_asset_source(settings, inventory[str(clip.asset_id)]),
            float(clip.source_in),
            float(clip.source_out),
        )
        for clip in plan.clips
    ]
    project_id = str(context["job"]["project_id"])
    job_id = str(context["job"]["id"])
    output_directory = settings.media_root / "exports" / project_id / job_id / f"v{version}"
    captions_path = output_directory / "captions.ass"
    preview_path = output_directory / "preview.mp4"
    manifest_path = output_directory / "manifest.json"

    events = caption_events(plan, context["assets"])
    _atomic_text(captions_path, render_ass(events))
    encoder = _render_video(sources, captions_path, preview_path, settings.analysis_command_timeout_seconds)

    document = plan.model_dump(mode="json")
    manifest = {
        "schema_version": "1.0",
        "job_id": job_id,
        "version": version,
        "recipe": "talking_head",
        "edit_plan_sha256": document_sha256(document),
        "editor": {"provider": provider, "model": model},
        "render": {
            "width": PREVIEW_WIDTH,
            "height": PREVIEW_HEIGHT,
            "frames_per_second": PREVIEW_FPS,
            "video_encoder": encoder,
            "audio_preset": "spoken_voice_v1",
            "caption_style": "clean_blue_v1",
        },
        "sources": [
            {
                "asset_id": str(clip.asset_id),
                "sha256": inventory[str(clip.asset_id)].get("sha256"),
                "source_in": clip.source_in,
                "source_out": clip.source_out,
            }
            for clip in plan.clips
        ],
        "outputs": {
            "preview": preview_path.relative_to(settings.media_root).as_posix(),
            "captions": captions_path.relative_to(settings.media_root).as_posix(),
        },
        "capacity_at_start": capacity,
        "content_policy": {
            "source_derived_only": True,
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }
    manifest["manifest_path"] = manifest_path.relative_to(settings.media_root).as_posix()
    _atomic_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest
