import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.edit_plan import TalkingHeadEditPlan, document_sha256
from app.editor_context import resolve_internal_asset_source
from app.media_analysis import (
    READ_ONLY_MODE,
    ensure_capacity,
    generate_file,
    probe_media,
    render_webvtt,
    resolve_source,
    run_command,
)


PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
PREVIEW_FPS = 30
FINAL_WIDTH = 1080
FINAL_HEIGHT = 1920
FINAL_FPS = 30


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
    plan: TalkingHeadEditPlan,
    assets: list[dict[str, Any]],
    corrections: list[dict[str, str]] | None = None,
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
            for correction in corrections or []:
                original_text = str(correction.get("original_text", ""))
                if original_text:
                    text = text.replace(
                        original_text,
                        str(correction.get("replacement_text", "")),
                    )
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


def render_ass(
    events: list[dict[str, Any]],
    *,
    width: int = PREVIEW_WIDTH,
    height: int = PREVIEW_HEIGHT,
) -> str:
    font_size = 34 if width == PREVIEW_WIDTH else 68
    outline = 3 if width == PREVIEW_WIDTH else 6
    shadow = 1 if width == PREVIEW_WIDTH else 2
    horizontal_margin = 38 if width == PREVIEW_WIDTH else 76
    vertical_margin = 86 if height == PREVIEW_HEIGHT else 172
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: GMBlue,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00B45B19,&H78000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{horizontal_margin},{horizontal_margin},{vertical_margin},1

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


def _clip_video_filter(
    *,
    index: int,
    duration: float,
    visual_preset: str,
    fade_in: bool,
    fade_out: bool,
    width: int,
    height: int,
    frames_per_second: int,
) -> str:
    chain = (
        f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    total_frames = max(1, round(duration * frames_per_second) - 1)
    if visual_preset == "punch_in":
        zoom = "1.12"
    elif visual_preset == "strong_punch_in":
        zoom = "1.18"
    elif visual_preset == "slow_push_in":
        zoom = f"min(1+0.12*on/{total_frames},1.12)"
    elif visual_preset == "slow_pull_out":
        zoom = f"max(1.12-0.12*on/{total_frames},1)"
    else:
        zoom = ""
    if zoom:
        chain += (
            f",zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={width}x{height}:fps={frames_per_second}"
        )
    else:
        chain += f",fps={frames_per_second}"
    transition_seconds = min(0.18, duration / 4)
    if fade_in:
        chain += f",fade=t=in:st=0:d={transition_seconds:.3f}"
    if fade_out:
        chain += f",fade=t=out:st={duration - transition_seconds:.3f}:d={transition_seconds:.3f}"
    return chain + f"[v{index}]"


def _ffmpeg_filter(
    plan: TalkingHeadEditPlan,
    captions_path: Path,
    *,
    width: int,
    height: int,
    frames_per_second: int,
    music_input_index: int | None = None,
) -> str:
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, clip in enumerate(plan.clips):
        duration = float(clip.source_out - clip.source_in)
        fade_in = index > 0 and clip.transition == "dip_to_black"
        fade_out = index + 1 < len(plan.clips) and plan.clips[index + 1].transition == "dip_to_black"
        filters.append(
            _clip_video_filter(
                index=index,
                duration=duration,
                visual_preset=clip.visual_preset,
                fade_in=fade_in,
                fade_out=fade_out,
                width=width,
                height=height,
                frames_per_second=frames_per_second,
            )
        )
        audio = f"[{index}:a:0]aresample=48000,asetpts=PTS-STARTPTS"
        transition_seconds = min(0.18, duration / 4)
        if fade_in:
            audio += f",afade=t=in:st=0:d={transition_seconds:.3f}"
        if fade_out:
            audio += (
                f",afade=t=out:st={duration - transition_seconds:.3f}"
                f":d={transition_seconds:.3f}"
            )
        filters.append(audio + f"[a{index}]")
        concat_inputs.extend((f"[v{index}]", f"[a{index}]"))
    filters.append(
        "".join(concat_inputs) + f"concat=n={len(plan.clips)}:v=1:a=1[vcat][acat]"
    )
    safe_caption_path = str(captions_path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
    filters.append(f"[vcat]subtitles=filename='{safe_caption_path}'[vout]")
    if music_input_index is None:
        filters.append("[acat]loudnorm=I=-16:LRA=11:TP=-1.5[aout]")
    else:
        total_duration = sum(float(clip.source_out - clip.source_in) for clip in plan.clips)
        fade_out_start = max(0.0, total_duration - 1.5)
        volume = "-30dB" if plan.music_mix == "subtle" else "-24dB"
        filters.append("[acat]loudnorm=I=-16:LRA=11:TP=-1.5,asplit=2[voice][key]")
        filters.append(
            f"[{music_input_index}:a:0]aresample=48000,atrim=0:{total_duration:.3f},"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1.000,"
            f"afade=t=out:st={fade_out_start:.3f}:d=1.500,volume={volume}[music]"
        )
        filters.append(
            "[music][key]sidechaincompress=threshold=0.020:ratio=10:attack=15:release=350[ducked]"
        )
        filters.append(
            "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    return ";".join(filters)


def _render_video(
    sources: list[tuple[Path, float, float]],
    plan: TalkingHeadEditPlan,
    captions_path: Path,
    destination: Path,
    timeout: int,
    *,
    width: int = PREVIEW_WIDTH,
    height: int = PREVIEW_HEIGHT,
    frames_per_second: int = PREVIEW_FPS,
    final_quality: bool = False,
    music_source: Path | None = None,
) -> str:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for source, source_in, source_out in sources:
        common.extend(
            ["-ss", f"{source_in:.3f}", "-t", f"{source_out - source_in:.3f}", "-i", str(source)]
        )
    if music_source is not None:
        common.extend(["-stream_loop", "-1", "-i", str(music_source)])
    common.extend(
        [
            "-filter_complex",
            _ffmpeg_filter(
                plan,
                captions_path,
                width=width,
                height=height,
                frames_per_second=frames_per_second,
                music_input_index=len(sources) if music_source is not None else None,
            ),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
        ]
    )
    encoders = (
        (
            "h264_nvenc",
            [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p5" if final_quality else "p4",
                "-cq",
                "19" if final_quality else "24",
                "-b:v",
                "0",
            ],
        ),
        (
            "libx264",
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18" if final_quality else "23",
            ],
        ),
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
                "192k" if final_quality else "128k",
                "-map_metadata",
                "-1",
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
        raise RuntimeError("video render failed with both NVENC and libx264")
    finally:
        temporary.unlink(missing_ok=True)


def _selected_music(
    context: dict[str, Any],
    plan: TalkingHeadEditPlan,
    settings: Settings,
) -> tuple[Path | None, dict[str, Any] | None]:
    if plan.music_track_id is None:
        return None, None
    track_id = str(plan.music_track_id)
    track = next(
        (
            candidate
            for candidate in context.get("music_library", [])
            if str(candidate.get("track_id")) == track_id
        ),
        None,
    )
    if track is None or not isinstance(track.get("_storage_key"), str):
        raise RuntimeError("the approved music track is unavailable to the renderer")
    public_track = {key: value for key, value in track.items() if not key.startswith("_")}
    public_track["mix"] = plan.music_mix
    return resolve_source(settings.media_root, track["_storage_key"]), public_track


def render_edit_preview(
    context: dict[str, Any],
    plan: TalkingHeadEditPlan,
    version: int,
    provider: str,
    model: str,
    caption_corrections: list[dict[str, str]] | None = None,
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
    music_source, music_metadata = _selected_music(context, plan, settings)
    project_id = str(context["job"]["project_id"])
    job_id = str(context["job"]["id"])
    output_directory = settings.media_root / "exports" / project_id / job_id / f"v{version}"
    captions_path = output_directory / "captions.ass"
    preview_path = output_directory / "preview.mp4"
    manifest_path = output_directory / "manifest.json"

    events = caption_events(plan, context["assets"], caption_corrections)
    _atomic_text(captions_path, render_ass(events))
    encoder = _render_video(
        sources,
        plan,
        captions_path,
        preview_path,
        settings.analysis_command_timeout_seconds,
        music_source=music_source,
    )

    document = plan.model_dump(mode="json")
    manifest = {
        "schema_version": "1.0",
        "job_id": job_id,
        "version": version,
        "recipe": "talking_head",
        "edit_plan_sha256": document_sha256(document),
        "editor": {"provider": provider, "model": model},
        "creative_direction": {
            "target_duration_seconds": context["job"].get("target_duration_seconds"),
            "edit_style": context["job"].get("edit_style"),
            "music_mode": context["job"].get("music_mode"),
            "target_platform": context["job"].get("target_platform"),
            "must_include": context["job"].get("must_include"),
        },
        "music": music_metadata,
        "caption_corrections": caption_corrections or [],
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
                "transition": clip.transition,
                "visual_preset": clip.visual_preset,
            }
            for clip in plan.clips
        ],
        "outputs": {
            "preview": preview_path.relative_to(settings.media_root).as_posix(),
            "captions": captions_path.relative_to(settings.media_root).as_posix(),
        },
        "capacity_at_start": capacity,
        "content_policy": {
            "source_derived_only": music_metadata is None,
            "approved_library_music": music_metadata is not None,
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }
    manifest["manifest_path"] = manifest_path.relative_to(settings.media_root).as_posix()
    _atomic_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffmpeg_version(timeout: int) -> str:
    completed = run_command(
        ["ffmpeg", "-hide_banner", "-version"],
        timeout=min(timeout, 30),
        check=False,
    )
    first_line = completed.stdout.strip().splitlines()[:1]
    return first_line[0][:300] if first_line else "unknown"


def _create_delivery_package(
    destination: Path,
    *,
    video_path: Path,
    captions_path: Path,
    cover_path: Path,
    manifest_path: Path,
    post_copy_path: Path | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "x") as archive:
            archive.write(video_path, "gm-studio-final.mp4", compress_type=zipfile.ZIP_STORED)
            archive.write(captions_path, "gm-studio-captions.vtt", compress_type=zipfile.ZIP_DEFLATED)
            archive.write(cover_path, "gm-studio-cover.jpg", compress_type=zipfile.ZIP_STORED)
            archive.write(manifest_path, "gm-studio-manifest.json", compress_type=zipfile.ZIP_DEFLATED)
            if post_copy_path is not None:
                archive.write(post_copy_path, "gm-studio-post-copy.txt", compress_type=zipfile.ZIP_DEFLATED)
        temporary.chmod(READ_ONLY_MODE)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def render_final_delivery(
    context: dict[str, Any],
    plan: TalkingHeadEditPlan,
    version: int,
    provider: str,
    model: str,
    caption_corrections: list[dict[str, str]],
    approved_at: str,
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
    music_source, music_metadata = _selected_music(context, plan, settings)
    project_id = str(context["job"]["project_id"])
    job_id = str(context["job"]["id"])
    output_directory = settings.media_root / "deliveries" / project_id / job_id / f"v{version}"
    captions_ass_path = output_directory / "captions.ass"
    captions_vtt_path = output_directory / "captions.vtt"
    video_path = output_directory / "final.mp4"
    cover_path = output_directory / "cover.jpg"
    post_copy_path = output_directory / "post-copy.txt"
    package_path = output_directory / "delivery.zip"
    manifest_path = output_directory / "manifest.json"

    events = caption_events(plan, context["assets"], caption_corrections)
    _atomic_text(
        captions_ass_path,
        render_ass(events, width=FINAL_WIDTH, height=FINAL_HEIGHT),
    )
    _atomic_text(captions_vtt_path, render_webvtt(events))
    encoder = _render_video(
        sources,
        plan,
        captions_ass_path,
        video_path,
        settings.analysis_command_timeout_seconds,
        width=FINAL_WIDTH,
        height=FINAL_HEIGHT,
        frames_per_second=FINAL_FPS,
        final_quality=True,
        music_source=music_source,
    )
    technical_probe = probe_media(video_path, settings.analysis_command_timeout_seconds)
    video_stream = next(
        (stream for stream in technical_probe["streams"] if stream.get("type") == "video"),
        None,
    )
    audio_stream = next(
        (stream for stream in technical_probe["streams"] if stream.get("type") == "audio"),
        None,
    )
    if video_stream is None or audio_stream is None:
        raise RuntimeError("final delivery QA requires both video and audio")
    if video_stream.get("width") != FINAL_WIDTH or video_stream.get("height") != FINAL_HEIGHT:
        raise RuntimeError("final delivery QA found an unexpected frame size")

    duration = float(technical_probe.get("format", {}).get("duration_seconds") or 0)
    cover_seek = min(1.0, max(0.0, duration / 2))
    generate_file(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{cover_seek:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-map_metadata",
            "-1",
        ],
        cover_path,
        settings.analysis_command_timeout_seconds,
    )

    document = plan.model_dump(mode="json")
    outputs = {
        "video": video_path.relative_to(settings.media_root).as_posix(),
        "captions": captions_vtt_path.relative_to(settings.media_root).as_posix(),
        "cover": cover_path.relative_to(settings.media_root).as_posix(),
        "package": package_path.relative_to(settings.media_root).as_posix(),
    }
    if plan.post_copy:
        _atomic_text(post_copy_path, plan.post_copy.strip() + "\n")
        outputs["post_copy"] = post_copy_path.relative_to(settings.media_root).as_posix()
    manifest = {
        "schema_version": "1.1",
        "job_id": job_id,
        "version": version,
        "approved_at": approved_at,
        "recipe": "talking_head",
        "edit_plan_sha256": document_sha256(document),
        "editor": {"provider": provider, "model": model},
        "creative_direction": {
            "target_duration_seconds": context["job"].get("target_duration_seconds"),
            "edit_style": context["job"].get("edit_style"),
            "music_mode": context["job"].get("music_mode"),
            "target_platform": context["job"].get("target_platform"),
            "must_include": context["job"].get("must_include"),
        },
        "music": music_metadata,
        "tools": {
            "gm_studio_core": "0.1.0",
            "ffmpeg": _ffmpeg_version(settings.analysis_command_timeout_seconds),
            "render_template": "talking_head_vertical_v1",
        },
        "render": {
            "width": FINAL_WIDTH,
            "height": FINAL_HEIGHT,
            "frames_per_second": FINAL_FPS,
            "video_encoder": encoder,
            "audio_preset": "spoken_voice_v1",
            "caption_style": "clean_blue_v1",
        },
        "caption_corrections": caption_corrections,
        "sources": [
            {
                "asset_id": str(clip.asset_id),
                "sha256": inventory[str(clip.asset_id)].get("sha256"),
                "source_in": clip.source_in,
                "source_out": clip.source_out,
                "transition": clip.transition,
                "visual_preset": clip.visual_preset,
            }
            for clip in plan.clips
        ],
        "outputs": outputs,
        "output_sha256": {
            "video": _file_sha256(video_path),
            "captions": _file_sha256(captions_vtt_path),
            "cover": _file_sha256(cover_path),
        },
        "quality_assurance": {
            "passed": True,
            "probe": technical_probe,
            "video_and_audio_present": True,
            "frame_size_verified": True,
        },
        "capacity_at_start": capacity,
        "content_policy": {
            "source_derived_only": music_metadata is None,
            "approved_library_music": music_metadata is not None,
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }
    if plan.post_copy:
        manifest["output_sha256"]["post_copy"] = _file_sha256(post_copy_path)
    manifest["manifest_path"] = manifest_path.relative_to(settings.media_root).as_posix()
    _atomic_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    _create_delivery_package(
        package_path,
        video_path=video_path,
        captions_path=captions_vtt_path,
        cover_path=cover_path,
        manifest_path=manifest_path,
        post_copy_path=post_copy_path if plan.post_copy else None,
    )
    return manifest
