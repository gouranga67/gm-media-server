import json
import os
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.edit_plan import MontageEditPlan, document_sha256
from app.edit_renderer import (
    _atomic_text,
    _create_delivery_package,
    _ffmpeg_version,
    _file_sha256,
    _selected_music,
    adjust_caption_timing,
    clip_caption_events,
    render_ass,
)
from app.editor_context import (
    resolve_internal_asset_render_source,
    resolve_internal_asset_source,
)
from app.effect_renderer import (
    append_effect_filters,
    effect_input_arguments,
    public_effect_manifest,
    selected_effects,
)
from app.media_analysis import (
    READ_ONLY_MODE,
    ensure_capacity,
    generate_file,
    hdr_to_sdr_filter,
    probe_media,
    render_webvtt,
    resolve_source,
    run_command,
    video_probe_hdr_mode,
)


def montage_caption_events(
    plan: MontageEditPlan,
    assets: list[dict[str, Any]],
    corrections: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Map audible source speech onto the assembled montage timeline."""

    inventory = {str(asset["asset_id"]): asset for asset in assets}
    events: list[dict[str, Any]] = []
    timeline_start = 0.0
    for clip in plan.clips:
        if clip.media_kind == "video" and clip.include_source_audio:
            source_in = float(clip.source_in)
            source_out = float(clip.source_out)
            events.extend(
                clip_caption_events(
                    inventory[str(clip.asset_id)],
                    source_in,
                    source_out,
                    timeline_start,
                    corrections,
                )
            )
        timeline_start += float(clip.duration)
    return events


def _subtitle_filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def _dimensions(aspect: str, *, final: bool) -> tuple[int, int]:
    if aspect == "landscape":
        return (1920, 1080) if final else (960, 540)
    if aspect == "square":
        return (1080, 1080) if final else (540, 540)
    return (1080, 1920) if final else (540, 960)


def _video_filter(
    index: int,
    duration: float,
    preset: str,
    is_image: bool,
    fade_in: bool,
    fade_out: bool,
    width: int,
    height: int,
    fps: int,
    hdr_mode: str | None = None,
) -> str:
    chain = f"[{index}:v:0]"
    if hdr_mode is not None:
        chain += hdr_to_sdr_filter(hdr_mode) + ","
    chain += (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    frame_count = max(1, round(duration * fps))
    final_frame = max(1, frame_count - 1)
    if preset == "punch_in":
        zoom = "1.10"
    elif preset == "slow_push_in":
        zoom = f"min(1+0.10*on/{final_frame},1.10)"
    elif preset == "slow_pull_out":
        zoom = f"max(1.10-0.10*on/{final_frame},1)"
    else:
        zoom = ""

    if is_image and zoom:
        # A still image is one decoded frame. zoompan expands that frame into
        # the whole clip, avoiding repeated decoding of a large JPEG.
        chain += (
            f",zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frame_count}:s={width}x{height}:fps={fps}"
        )
    elif is_image:
        chain += f",tpad=stop_mode=clone:stop_duration={duration:.3f},fps={fps}"
    elif zoom:
        chain += (
            ",setpts=PTS-STARTPTS"
            f",zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={width}x{height}:fps={fps}"
        )
    else:
        chain += f",setpts=PTS-STARTPTS,fps={fps}"
    # Phone files can report a container duration that is slightly longer than
    # the usable video stream. Hold the final decoded frame so every segment
    # still occupies the exact duration approved in the edit plan.
    chain += (
        f",tpad=stop_mode=clone:stop_duration={duration:.3f}"
        f",trim=duration={duration:.3f},setpts=PTS-STARTPTS"
    )
    transition = min(0.2, duration / 4)
    if fade_in:
        chain += f",fade=t=in:st=0:d={transition:.3f}"
    if fade_out:
        chain += f",fade=t=out:st={duration - transition:.3f}:d={transition:.3f}"
    return chain + f",format=yuv420p[v{index}]"


def _filter_graph(
    plan: MontageEditPlan,
    assets: dict[str, dict[str, Any]],
    *,
    width: int,
    height: int,
    fps: int,
    music_input_index: int | None,
    captions_path: Path | None = None,
    hdr_modes: list[str | None] | None = None,
) -> str:
    filters: list[str] = []
    concat_inputs: list[str] = []
    total_duration = sum(float(clip.duration) for clip in plan.clips)
    for index, clip in enumerate(plan.clips):
        duration = float(clip.duration)
        fade_in = index > 0 and clip.transition == "dip_to_black"
        fade_out = index + 1 < len(plan.clips) and plan.clips[index + 1].transition == "dip_to_black"
        filters.append(
            _video_filter(
                index,
                duration,
                clip.visual_preset,
                clip.media_kind == "image",
                fade_in,
                fade_out,
                width,
                height,
                fps,
                hdr_mode=hdr_modes[index] if hdr_modes else None,
            )
        )
        asset = assets[str(clip.asset_id)]
        if clip.media_kind == "video" and clip.include_source_audio and asset.get("has_audio"):
            edge_fade = min(0.08, duration / 8)
            source_volume_db = -8.0 + float(clip.source_audio_gain_db)
            audio = (
                f"[{index}:a:0]aresample=48000,atrim=0:{duration:.3f},"
                f"apad=pad_dur={duration:.3f},atrim=0:{duration:.3f},"
                "asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:"
                f"sample_rates=48000:channel_layouts=stereo,volume={source_volume_db:.3f}dB,"
                f"afade=t=in:st=0:d={edge_fade:.3f},"
                f"afade=t=out:st={duration - edge_fade:.3f}:d={edge_fade:.3f}"
            )
        else:
            audio = (
                f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.3f},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
            )
        transition = min(0.2, duration / 4)
        if fade_in:
            audio += f",afade=t=in:st=0:d={transition:.3f}"
        if fade_out:
            audio += f",afade=t=out:st={duration - transition:.3f}:d={transition:.3f}"
        filters.append(audio + f"[a{index}]")
        concat_inputs.extend((f"[v{index}]", f"[a{index}]"))
    filters.append("".join(concat_inputs) + f"concat=n={len(plan.clips)}:v=1:a=1[vcat][acat]")
    video_output = "vbase" if captions_path is not None else "vout"
    filters.append(
        f"[vcat]tpad=stop_mode=clone:stop_duration={total_duration:.3f},"
        f"trim=duration={total_duration:.3f},setpts=PTS-STARTPTS[{video_output}]"
    )
    if captions_path is not None:
        filters.append(
            f"[vbase]subtitles=filename='{_subtitle_filter_path(captions_path)}'[vout]"
        )
    if music_input_index is None:
        filters.append(
            f"[acat]apad=pad_dur={total_duration:.3f},"
            f"atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,"
            "loudnorm=I=-16:LRA=11:TP=-1.5,"
            f"apad=pad_dur={total_duration:.3f},atrim=0:{total_duration:.3f}[aout]"
        )
    else:
        fade_out_start = max(0.0, total_duration - 1.5)
        volume = "-9dB" if plan.music_mix == "subtle" else "-4dB"
        filters.append(
            f"[acat]apad=pad_dur={total_duration:.3f},"
            f"atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "asplit=2[source][key]"
        )
        filters.append(
            f"[{music_input_index}:a:0]aresample=48000,atrim=0:{total_duration:.3f},"
            "loudnorm=I=-18:LRA=11:TP=-1.5,"
            "aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.750,"
            f"afade=t=out:st={fade_out_start:.3f}:d=1.500,volume={volume}[music]"
        )
        filters.append(
            "[music][key]sidechaincompress=threshold=0.080:ratio=4:attack=15:release=350[ducked]"
        )
        filters.append(
            "[source][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "loudnorm=I=-14:LRA=11:TP=-1.0,"
            f"apad=pad_dur={total_duration:.3f},atrim=0:{total_duration:.3f}[aout]"
        )
    return ";".join(filters)


def _timing_error(probe: dict[str, Any], expected_duration: float) -> str | None:
    durations = {
        str(stream.get("type")): stream.get("duration_seconds")
        for stream in probe.get("streams", [])
    }
    video_duration = durations.get("video")
    audio_duration = durations.get("audio")
    if not isinstance(video_duration, (int, float)) or not isinstance(audio_duration, (int, float)):
        return "render timing QA could not read both stream durations"
    tolerance = 0.15
    if abs(float(video_duration) - expected_duration) > tolerance:
        return f"video is {float(video_duration):.3f}s; expected {expected_duration:.3f}s"
    if abs(float(audio_duration) - expected_duration) > tolerance:
        return f"audio is {float(audio_duration):.3f}s; expected {expected_duration:.3f}s"
    if abs(float(video_duration) - float(audio_duration)) > tolerance:
        return (
            f"audio/video differ by {abs(float(video_duration) - float(audio_duration)):.3f}s"
        )
    return None


def _render_source(
    settings: Settings, asset: dict[str, Any], *, media_kind: str
) -> Path:
    if media_kind == "image":
        preview_key = asset.get("_preview_key")
        if isinstance(preview_key, str):
            # Image analysis creates a clean, metadata-stripped JPEG. Some
            # phone JPEGs contain malformed APP fields that decode once during
            # ingest but fail when several originals are opened in one render.
            return resolve_source(settings.media_root, preview_key)
        return resolve_internal_asset_source(settings, asset)
    return resolve_internal_asset_render_source(settings, asset)


def _ffmpeg_failure_detail(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    useful = [
        line
        for line in lines
        if line not in {"Conversion failed!", "Error while filtering: Invalid argument"}
    ]
    selected = (useful or lines)[-4:]
    return " | ".join(selected)[:700] or "FFmpeg returned no diagnostic detail"


def _render(
    context: dict[str, Any],
    plan: MontageEditPlan,
    destination: Path,
    *,
    width: int,
    height: int,
    final: bool,
    settings: Settings,
    captions_path: Path | None = None,
) -> str:
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    render_sources: list[Path] = []
    for clip in plan.clips:
        source = _render_source(
            settings,
            inventory[str(clip.asset_id)],
            media_kind=clip.media_kind,
        )
        render_sources.append(source)
        if clip.media_kind == "image":
            common.extend(["-i", str(source)])
        else:
            common.extend(
                [
                    "-ss",
                    f"{clip.source_in:.3f}",
                    "-t",
                    f"{clip.duration:.3f}",
                    "-i",
                    str(source),
                ]
            )
    music_source, _ = _selected_music(context, plan, settings)
    if music_source is not None:
        common.extend(["-stream_loop", "-1", "-i", str(music_source)])
    effect_sources = selected_effects(
        context, plan, settings, len(plan.clips) + (1 if music_source is not None else 0)
    )
    common.extend(effect_input_arguments(effect_sources))
    probe_cache: dict[Path, str | None] = {}
    hdr_modes: list[str | None] = []
    for source, clip in zip(render_sources, plan.clips, strict=True):
        if clip.media_kind == "image":
            hdr_modes.append(None)
            continue
        if source not in probe_cache:
            probe_cache[source] = video_probe_hdr_mode(
                probe_media(source, settings.analysis_command_timeout_seconds)
            )
        hdr_modes.append(probe_cache[source])
    common.extend(
        [
            "-filter_complex",
            append_effect_filters(_filter_graph(
                plan,
                inventory,
                width=width,
                height=height,
                fps=30,
                music_input_index=len(plan.clips) if music_source is not None else None,
                captions_path=captions_path,
                hdr_modes=hdr_modes,
            ), effect_sources, width=width, height=height,
                total_duration=sum(float(clip.duration) for clip in plan.clips)),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
        ]
    )
    encoders = (
        (
            "h264_nvenc",
            ["-c:v", "h264_nvenc", "-preset", "p5" if final else "p4", "-cq", "19" if final else "24", "-b:v", "0"],
        ),
        (
            "libx264",
            ["-c:v", "libx264", "-preset", "medium", "-crf", "18" if final else "23"],
        ),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.part{destination.suffix}")
    temporary.unlink(missing_ok=True)
    expected_duration = sum(float(clip.duration) for clip in plan.clips)
    failures: list[str] = []
    try:
        for encoder, arguments in encoders:
            temporary.unlink(missing_ok=True)
            completed = run_command(
                [
                    *common,
                    *arguments,
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k" if final else "128k",
                    "-color_primaries",
                    "bt709",
                    "-color_trc",
                    "bt709",
                    "-colorspace",
                    "bt709",
                    "-color_range",
                    "tv",
                    "-map_metadata",
                    "-1",
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ],
                timeout=settings.analysis_command_timeout_seconds,
                check=False,
            )
            if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                timing_error = _timing_error(
                    probe_media(temporary, settings.analysis_command_timeout_seconds),
                    expected_duration,
                )
                if timing_error is not None:
                    failures.append(f"{encoder}: {timing_error}")
                    continue
                temporary.chmod(READ_ONLY_MODE)
                os.replace(temporary, destination)
                return encoder
            failures.append(f"{encoder}: {_ffmpeg_failure_detail(completed.stderr)}")
        raise RuntimeError("montage render failed: " + "; ".join(failures))
    finally:
        temporary.unlink(missing_ok=True)


def _manifest(
    context: dict[str, Any],
    plan: MontageEditPlan,
    version: int,
    provider: str,
    model: str,
    encoder: str,
    width: int,
    height: int,
    outputs: dict[str, str],
    capacity: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    _, music = _selected_music(context, plan, settings)
    effects = selected_effects(context, plan, settings, 0)
    document = plan.model_dump(mode="json")
    return {
        "schema_version": "1.0",
        "job_id": str(context["job"]["id"]),
        "version": version,
        "recipe": "montage",
        "edit_plan_sha256": document_sha256(document),
        "editor": {"provider": provider, "model": model},
        "creative_direction": {
            "target_duration_seconds": context["job"].get("target_duration_seconds"),
            "edit_style": context["job"].get("edit_style"),
            "music_mode": context["job"].get("music_mode"),
            "selected_music_track_id": context["job"].get("selected_music_track_id"),
            "effect_level": context["job"].get("effect_level"),
            "target_platform": context["job"].get("target_platform"),
            "output_aspect": context["job"].get("output_aspect"),
            "must_include": context["job"].get("must_include"),
            "audience": context["job"].get("audience"),
            "story_goal": context["job"].get("story_goal"),
            "desired_feeling": context["job"].get("desired_feeling"),
            "ending_instruction": context["job"].get("ending_instruction"),
            "cover_time_seconds": context["job"].get("cover_time_seconds"),
        },
        "story_assessment": context.get("story_spine", {}).get("engagement_assessment", {}),
        "music": music,
        "creative_effects": public_effect_manifest(effects),
        "render": {
            "width": width,
            "height": height,
            "frames_per_second": 30,
            "video_encoder": encoder,
            "audio_preset": "montage_mix_v1",
            "color_pipeline": "transfer_aware_hdr_to_bt709_sdr_v2",
        },
        "sources": [
            {
                "asset_id": str(clip.asset_id),
                "sha256": inventory[str(clip.asset_id)].get("sha256"),
                "media_kind": clip.media_kind,
                "source_in": clip.source_in,
                "source_out": clip.source_out,
                "duration": clip.duration,
                "transition": clip.transition,
                "visual_preset": clip.visual_preset,
                "include_source_audio": clip.include_source_audio,
                "source_audio_gain_db": clip.source_audio_gain_db,
                "story_role": clip.story_role,
                "editorial_intent": clip.editorial_intent,
                "render_basis": (
                    "normalized_image_preview"
                    if clip.media_kind == "image" and inventory[str(clip.asset_id)].get("_preview_key")
                    else "normalized_video_proxy"
                    if clip.media_kind == "video" and inventory[str(clip.asset_id)].get("_proxy_key")
                    else "original"
                ),
            }
            for clip in plan.clips
        ],
        "outputs": outputs,
        "capacity_at_start": capacity,
        "content_policy": {
            "source_derived_only": music is None and not effects,
            "approved_library_music": music is not None,
            "approved_library_effects": bool(effects),
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }


def render_montage_preview(
    context: dict[str, Any],
    plan: MontageEditPlan,
    version: int,
    provider: str,
    model: str,
    caption_corrections: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    capacity = ensure_capacity(settings)
    width, height = _dimensions(str(context["job"].get("output_aspect") or "vertical"), final=False)
    directory = settings.media_root / "exports" / str(context["job"]["project_id"]) / str(context["job"]["id"]) / f"v{version}"
    preview = directory / "preview.mp4"
    captions_ass = directory / "captions.ass"
    manifest_path = directory / "manifest.json"
    events = adjust_caption_timing(
        montage_caption_events(plan, context["assets"], caption_corrections),
        float(plan.caption_timing_offset_seconds),
    )
    if events:
        _atomic_text(
            captions_ass,
            render_ass(
                events, width=width, height=height,
                brand_kit=context.get("brand_kit"), position=plan.caption_position,
                target_platform=str(context["job"].get("target_platform") or "all_social"),
            ),
        )
    encoder = _render(
        context,
        plan,
        preview,
        width=width,
        height=height,
        final=False,
        settings=settings,
        captions_path=captions_ass if events else None,
    )
    manifest = _manifest(
        context,
        plan,
        version,
        provider,
        model,
        encoder,
        width,
        height,
        {"preview": preview.relative_to(settings.media_root).as_posix()},
        capacity,
        settings,
    )
    manifest["manifest_path"] = manifest_path.relative_to(settings.media_root).as_posix()
    manifest["captions"] = {
        "style": "clean_blue_v1",
        "events": len(events),
        "source_speech_only": True,
        "position": plan.caption_position,
        "timing_offset_seconds": plan.caption_timing_offset_seconds,
        "platform_safe": True,
    }
    manifest["brand_kit"] = context.get("brand_kit")
    _atomic_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def render_montage_delivery(
    context: dict[str, Any],
    plan: MontageEditPlan,
    version: int,
    provider: str,
    model: str,
    caption_corrections: list[dict[str, str]] | None,
    approved_at: str,
    settings: Settings | None = None,
    delivery_slug: str | None = None,
    variant_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    capacity = ensure_capacity(settings)
    width, height = _dimensions(str(context["job"].get("output_aspect") or "vertical"), final=True)
    directory = settings.media_root / "deliveries" / str(context["job"]["project_id"]) / str(context["job"]["id"]) / f"v{version}"
    if delivery_slug:
        directory = directory / "variants" / delivery_slug
    video = directory / "final.mp4"
    captions = directory / "captions.vtt"
    captions_ass = directory / "captions.ass"
    cover = directory / "cover.jpg"
    post_copy = directory / "post-copy.txt"
    package = directory / "delivery.zip"
    manifest_path = directory / "manifest.json"
    events = adjust_caption_timing(
        montage_caption_events(plan, context["assets"], caption_corrections),
        float(plan.caption_timing_offset_seconds),
    )
    _atomic_text(captions, render_webvtt(events))
    if events:
        _atomic_text(
            captions_ass,
            render_ass(
                events, width=width, height=height,
                brand_kit=context.get("brand_kit"), position=plan.caption_position,
                target_platform=str(context["job"].get("target_platform") or "all_social"),
            ),
        )
    encoder = _render(
        context,
        plan,
        video,
        width=width,
        height=height,
        final=True,
        settings=settings,
        captions_path=captions_ass if events else None,
    )
    probe = probe_media(video, settings.analysis_command_timeout_seconds)
    video_stream = next((stream for stream in probe["streams"] if stream.get("type") == "video"), None)
    audio_stream = next((stream for stream in probe["streams"] if stream.get("type") == "audio"), None)
    if video_stream is None or audio_stream is None:
        raise RuntimeError("final montage QA requires video and audio")
    if video_stream.get("width") != width or video_stream.get("height") != height:
        raise RuntimeError("final montage QA found an unexpected frame size")
    cover_seek = min(
        float(context["job"].get("cover_time_seconds") or 0),
        max(0.0, float(probe.get("format", {}).get("duration_seconds") or 0) - 0.05),
    )
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
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-map_metadata",
            "-1",
        ],
        cover,
        settings.analysis_command_timeout_seconds,
    )
    outputs = {
        "video": video.relative_to(settings.media_root).as_posix(),
        "captions": captions.relative_to(settings.media_root).as_posix(),
        "cover": cover.relative_to(settings.media_root).as_posix(),
        "package": package.relative_to(settings.media_root).as_posix(),
    }
    if plan.post_copy:
        _atomic_text(post_copy, plan.post_copy.strip() + "\n")
        outputs["post_copy"] = post_copy.relative_to(settings.media_root).as_posix()
    manifest = _manifest(
        context,
        plan,
        version,
        provider,
        model,
        encoder,
        width,
        height,
        outputs,
        capacity,
        settings,
    )
    manifest.update(
        {
            "approved_at": approved_at,
            "captions": {
                "style": "clean_blue_v1",
                "events": len(events),
                "source_speech_only": True,
                "corrections": caption_corrections or [],
                "position": plan.caption_position,
                "timing_offset_seconds": plan.caption_timing_offset_seconds,
                "platform_safe": True,
            },
            "brand_kit": context.get("brand_kit"),
            "tools": {
                "gm_studio_core": "0.2.0",
                "ffmpeg": _ffmpeg_version(settings.analysis_command_timeout_seconds),
                "render_template": "montage_v1",
            },
            "output_sha256": {
                "video": _file_sha256(video),
                "captions": _file_sha256(captions),
                "cover": _file_sha256(cover),
            },
            "quality_assurance": {
                "passed": True,
                "probe": probe,
                "video_and_audio_present": True,
                "frame_size_verified": True,
                "caption_events": len(events),
            },
        }
    )
    if plan.post_copy:
        manifest["output_sha256"]["post_copy"] = _file_sha256(post_copy)
    if variant_metadata is not None:
        manifest["delivery_variant"] = variant_metadata
    manifest["manifest_path"] = manifest_path.relative_to(settings.media_root).as_posix()
    _atomic_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    _create_delivery_package(
        package,
        video_path=video,
        captions_path=captions,
        cover_path=cover,
        manifest_path=manifest_path,
        post_copy_path=post_copy if plan.post_copy else None,
    )
    return manifest
