import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from app.caption_text import replace_caption_phrase
from app.config import Settings, get_settings
from app.edit_plan import TalkingHeadEditPlan, document_sha256
from app.editor_context import resolve_internal_asset_render_source
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


PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
PREVIEW_FPS = 30
FINAL_WIDTH = 1080
FINAL_HEIGHT = 1920
FINAL_FPS = 30
CAPTION_MAX_WORDS = 7
CAPTION_MAX_CHARACTERS = 44
CAPTION_MAX_SECONDS = 2.6


def _delivery_dimensions(aspect: str) -> tuple[int, int]:
    if aspect == "landscape":
        return 1920, 1080
    if aspect == "square":
        return 1080, 1080
    return FINAL_WIDTH, FINAL_HEIGHT


def _preview_dimensions(aspect: str) -> tuple[int, int]:
    width, height = _delivery_dimensions(aspect)
    return width // 2, height // 2


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


def _correct_caption_text(
    text: str, corrections: list[dict[str, str]] | None
) -> str:
    for correction in corrections or []:
        original_text = str(correction.get("original_text", ""))
        if original_text:
            text = replace_caption_phrase(
                text,
                original_text,
                str(correction.get("replacement_text", "")),
            )
    return " ".join(text.split())


def clip_caption_events(
    asset: dict[str, Any],
    source_in: float,
    source_out: float,
    timeline_start: float,
    corrections: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Create short, source-timed caption cards for one assembled clip."""

    events: list[dict[str, Any]] = []
    for segment in asset.get("transcript_segments", []):
        try:
            segment_start = float(segment["start"])
            segment_end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        visible_start = max(segment_start, source_in)
        visible_end = min(segment_end, source_out)
        if visible_end - visible_start < 0.08:
            continue

        words: list[dict[str, Any]] = []
        for raw_word in segment.get("words", []):
            if not isinstance(raw_word, dict):
                continue
            try:
                word_start = float(raw_word["start"])
                word_end = float(raw_word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            text = " ".join(str(raw_word.get("text") or "").split())
            if text and word_end > source_in and word_start < source_out:
                words.append({"start": max(word_start, source_in), "end": min(word_end, source_out), "text": text})

        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for word in words:
            candidate_text = " ".join([*(item["text"] for item in current), word["text"]])
            pause = float(word["start"]) - float(current[-1]["end"]) if current else 0.0
            span = float(word["end"]) - float(current[0]["start"]) if current else 0.0
            if current and (
                len(current) >= CAPTION_MAX_WORDS
                or len(candidate_text) > CAPTION_MAX_CHARACTERS
                or span > CAPTION_MAX_SECONDS
                or pause >= 0.38
            ):
                groups.append(current)
                current = []
            current.append(word)
        if current:
            groups.append(current)

        if not groups:
            # Older imported transcripts may not have word timestamps. Divide the
            # segment into readable cards and distribute them across its duration.
            tokens = str(segment.get("text") or "").split()
            if tokens and segment_end > segment_start:
                first = max(
                    0,
                    min(
                        len(tokens) - 1,
                        int((visible_start - segment_start) / (segment_end - segment_start) * len(tokens)),
                    ),
                )
                last = max(
                    first + 1,
                    min(
                        len(tokens),
                        int((visible_end - segment_start) / (segment_end - segment_start) * len(tokens) + 0.999),
                    ),
                )
                tokens = tokens[first:last]
            cards = [tokens[index:index + CAPTION_MAX_WORDS] for index in range(0, len(tokens), CAPTION_MAX_WORDS)]
            if not cards:
                continue
            card_duration = (visible_end - visible_start) / len(cards)
            groups = [
                [{
                    "start": visible_start + index * card_duration,
                    "end": visible_start + (index + 1) * card_duration,
                    "text": " ".join(card),
                }]
                for index, card in enumerate(cards)
            ]

        for group in groups:
            text = _correct_caption_text(
                " ".join(str(word["text"]) for word in group), corrections
            )
            start = max(source_in, float(group[0]["start"]))
            end = min(source_out, float(group[-1]["end"]))
            if text and end - start >= 0.08:
                events.append(
                    {
                        "start": timeline_start + start - source_in,
                        "end": timeline_start + end - source_in,
                        "text": text,
                    }
                )
    return events


def caption_events(
    plan: TalkingHeadEditPlan,
    assets: list[dict[str, Any]],
    corrections: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Map short source transcript cards to the assembled preview timeline."""

    inventory = {str(asset["asset_id"]): asset for asset in assets}
    events: list[dict[str, Any]] = []
    timeline_start = 0.0
    for clip in plan.clips:
        source_in = float(clip.source_in)
        source_out = float(clip.source_out)
        asset = inventory[str(clip.asset_id)]
        events.extend(
            clip_caption_events(asset, source_in, source_out, timeline_start, corrections)
        )
        timeline_start += source_out - source_in
    return events


def adjust_caption_timing(
    events: list[dict[str, Any]], offset_seconds: float
) -> list[dict[str, Any]]:
    """Shift caption cues without changing the underlying edit timeline."""

    adjusted: list[dict[str, Any]] = []
    for event in events:
        start = max(0.0, float(event["start"]) + offset_seconds)
        end = max(start + 0.08, float(event["end"]) + offset_seconds)
        adjusted.append({**event, "start": start, "end": end})
    return adjusted


def render_ass(
    events: list[dict[str, Any]],
    *,
    width: int = PREVIEW_WIDTH,
    height: int = PREVIEW_HEIGHT,
    brand_kit: dict[str, Any] | None = None,
    position: str = "lower_safe",
    target_platform: str = "all_social",
) -> str:
    # Scale from frame height so the same caption style remains proportional
    # for both vertical reels and landscape montages.
    scale = height / PREVIEW_HEIGHT
    style = str((brand_kit or {}).get("caption_style") or "clean")
    font_size = max(18, round((30 if style == "minimal" else 34 if style == "clean" else 38) * scale))
    outline = max(1, round(3 * scale))
    shadow = max(1, round(scale))
    is_vertical = height > width
    horizontal_margin = (
        max(24, round(width * 0.12))
        if is_vertical
        else max(24, round(38 * width / PREVIEW_WIDTH))
    )
    if position == "upper":
        alignment = 8
        vertical_margin = max(32, round(height * (0.14 if is_vertical else 0.1)))
    elif position == "middle":
        alignment = 5
        vertical_margin = 0
    else:
        alignment = 2
        safe_ratio = (
            0.28
            if target_platform == "tiktok"
            else 0.24
            if target_platform == "instagram"
            else 0.25
        )
        vertical_margin = max(32, round(height * safe_ratio)) if is_vertical else max(32, round(86 * scale))
    font = {"sans": "DejaVu Sans", "serif": "DejaVu Serif", "mono": "DejaVu Sans Mono"}.get(str((brand_kit or {}).get("font_family")), "Arial")
    accent = str((brand_kit or {}).get("accent_color") or "#195BB4")
    red, green, blue = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
    ass_accent = f"&H00{blue:02X}{green:02X}{red:02X}"
    bold = 0 if style == "minimal" else -1
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: GMBlue,{font},{font_size},&H00FFFFFF,&H00FFFFFF,{ass_accent},&H78000000,{bold},0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},{horizontal_margin},{horizontal_margin},{vertical_margin},1

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
    hdr_mode: str | None = None,
) -> str:
    chain = f"[{index}:v:0]"
    if hdr_mode is not None:
        chain += hdr_to_sdr_filter(hdr_mode) + ","
    chain += (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,setpts=PTS-STARTPTS"
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
    chain += (
        f",tpad=stop_mode=clone:stop_duration={duration:.3f},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p"
    )
    return chain + f"[v{index}]"


def _ffmpeg_filter(
    plan: TalkingHeadEditPlan,
    captions_path: Path,
    *,
    width: int,
    height: int,
    frames_per_second: int,
    music_input_index: int | None = None,
    hdr_modes: list[str | None] | None = None,
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
                hdr_mode=hdr_modes[index] if hdr_modes else None,
            )
        )
        audio = (
            f"[{index}:a:0]aresample=48000,atrim=0:{duration:.3f},"
            f"apad=pad_dur={duration:.3f},atrim=0:{duration:.3f},"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS"
        )
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
        volume = "-9dB" if plan.music_mix == "subtle" else "-4dB"
        filters.append(
            "[acat]loudnorm=I=-16:LRA=11:TP=-1.5,aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "asplit=2[voice][key]"
        )
        filters.append(
            f"[{music_input_index}:a:0]aresample=48000,atrim=0:{total_duration:.3f},"
            "loudnorm=I=-18:LRA=11:TP=-1.5,"
            "aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1.000,"
            f"afade=t=out:st={fade_out_start:.3f}:d=1.500,volume={volume}[music]"
        )
        filters.append(
            "[music][key]sidechaincompress=threshold=0.080:ratio=4:attack=15:release=350[ducked]"
        )
        filters.append(
            "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    return ";".join(filters)


def _ffmpeg_failure_detail(stderr: str) -> str:
    """Return the useful tail of FFmpeg stderr without flooding the job screen."""

    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    boilerplate = {
        "Conversion failed!",
        "Error while filtering: Invalid argument",
    }
    useful = [line for line in lines if line not in boilerplate]
    diagnostic_markers = (
        "Parsed_",
        "auto_",
        "Input link",
        "Failed to configure",
        "Error reinitializing filters",
        "Failed to inject frame",
        "Error while processing",
    )
    diagnostics = [
        line for line in useful if any(marker in line for marker in diagnostic_markers)
    ]
    selected = (diagnostics or useful or lines)[-6:]
    return " | ".join(selected)[:700] or "FFmpeg returned no diagnostic detail"


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
    effect_sources: list[dict[str, Any]] | None = None,
) -> str:
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for source, source_in, source_out in sources:
        common.extend(
            ["-ss", f"{source_in:.3f}", "-t", f"{source_out - source_in:.3f}", "-i", str(source)]
        )
    if music_source is not None:
        common.extend(["-stream_loop", "-1", "-i", str(music_source)])
    effects = effect_sources or []
    common.extend(effect_input_arguments(effects))
    probe_cache: dict[Path, str | None] = {}
    hdr_modes: list[str | None] = []
    for source, _, _ in sources:
        if source not in probe_cache:
            probe_cache[source] = video_probe_hdr_mode(probe_media(source, timeout))
        hdr_modes.append(probe_cache[source])
    common.extend(
        [
            "-filter_complex",
            append_effect_filters(_ffmpeg_filter(
                plan,
                captions_path,
                width=width,
                height=height,
                frames_per_second=frames_per_second,
                music_input_index=len(sources) if music_source is not None else None,
                hdr_modes=hdr_modes,
            ), effects, width=width, height=height,
                total_duration=sum(float(clip.source_out - clip.source_in) for clip in plan.clips)),
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
    failures: list[str] = []
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
            ]
            completed = run_command(command, timeout=timeout, check=False)
            if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                temporary.chmod(READ_ONLY_MODE)
                os.replace(temporary, destination)
                return encoder
            failures.append(f"{encoder}: {_ffmpeg_failure_detail(completed.stderr)}")
            if encoder == "h264_nvenc":
                print("NVENC preview render unavailable; using libx264 fallback", flush=True)
        raise RuntimeError("video render failed: " + "; ".join(failures))
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
            resolve_internal_asset_render_source(settings, inventory[str(clip.asset_id)]),
            float(clip.source_in),
            float(clip.source_out),
        )
        for clip in plan.clips
    ]
    music_source, music_metadata = _selected_music(context, plan, settings)
    effect_sources = selected_effects(
        context, plan, settings, len(sources) + (1 if music_source is not None else 0)
    )
    project_id = str(context["job"]["project_id"])
    job_id = str(context["job"]["id"])
    output_directory = settings.media_root / "exports" / project_id / job_id / f"v{version}"
    captions_path = output_directory / "captions.ass"
    preview_path = output_directory / "preview.mp4"
    manifest_path = output_directory / "manifest.json"
    width, height = _preview_dimensions(str(context["job"].get("output_aspect") or "vertical"))

    events = adjust_caption_timing(
        caption_events(plan, context["assets"], caption_corrections),
        float(plan.caption_timing_offset_seconds),
    )
    _atomic_text(
        captions_path,
        render_ass(
            events,
            width=width,
            height=height,
            brand_kit=context.get("brand_kit"),
            position=plan.caption_position,
            target_platform=str(context["job"].get("target_platform") or "all_social"),
        ),
    )
    encoder = _render_video(
        sources,
        plan,
        captions_path,
        preview_path,
        settings.analysis_command_timeout_seconds,
        width=width,
        height=height,
        music_source=music_source,
        effect_sources=effect_sources,
    )

    document = plan.model_dump(mode="json")
    manifest = {
        "schema_version": "1.0",
        "job_id": job_id,
        "version": version,
        "recipe": "talking_head",
        "edit_plan_sha256": document_sha256(document),
        "editor": {"provider": provider, "model": model},
        "revision_report": context.get("revision_report"),
        "creative_direction": {
            "target_duration_seconds": context["job"].get("target_duration_seconds"),
            "edit_style": context["job"].get("edit_style"),
            "music_mode": context["job"].get("music_mode"),
            "selected_music_track_id": context["job"].get("selected_music_track_id"),
            "effect_level": context["job"].get("effect_level"),
            "target_platform": context["job"].get("target_platform"),
            "must_include": context["job"].get("must_include"),
            "audience": context["job"].get("audience"),
            "story_goal": context["job"].get("story_goal"),
            "desired_feeling": context["job"].get("desired_feeling"),
            "ending_instruction": context["job"].get("ending_instruction"),
            "cover_time_seconds": context["job"].get("cover_time_seconds"),
        },
        "story_assessment": context.get("story_spine", {}).get("engagement_assessment", {}),
        "music": music_metadata,
        "creative_effects": public_effect_manifest(effect_sources),
        "brand_kit": context.get("brand_kit"),
        "caption_corrections": caption_corrections or [],
        "captions": {
            "style": "clean_blue_v1",
            "events": len(events),
            "position": plan.caption_position,
            "timing_offset_seconds": plan.caption_timing_offset_seconds,
            "platform_safe": True,
        },
        "render": {
            "width": width,
            "height": height,
            "frames_per_second": PREVIEW_FPS,
            "video_encoder": encoder,
            "audio_preset": "spoken_voice_v1",
            "caption_style": "clean_blue_v1",
            "color_pipeline": "transfer_aware_hdr_to_bt709_sdr_v2",
        },
        "sources": [
            {
                "asset_id": str(clip.asset_id),
                "sha256": inventory[str(clip.asset_id)].get("sha256"),
                "source_in": clip.source_in,
                "source_out": clip.source_out,
                "transition": clip.transition,
                "visual_preset": clip.visual_preset,
                "story_role": clip.story_role,
                "editorial_intent": clip.editorial_intent,
                "render_basis": (
                    "normalized_video_proxy"
                    if inventory[str(clip.asset_id)].get("_proxy_key")
                    else "original"
                ),
            }
            for clip in plan.clips
        ],
        "outputs": {
            "preview": preview_path.relative_to(settings.media_root).as_posix(),
            "captions": captions_path.relative_to(settings.media_root).as_posix(),
        },
        "capacity_at_start": capacity,
        "content_policy": {
            "source_derived_only": music_metadata is None and not effect_sources,
            "approved_library_music": music_metadata is not None,
            "approved_library_effects": bool(effect_sources),
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
    delivery_slug: str | None = None,
    variant_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    capacity = ensure_capacity(settings)
    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    sources = [
        (
            resolve_internal_asset_render_source(settings, inventory[str(clip.asset_id)]),
            float(clip.source_in),
            float(clip.source_out),
        )
        for clip in plan.clips
    ]
    music_source, music_metadata = _selected_music(context, plan, settings)
    effect_sources = selected_effects(
        context, plan, settings, len(sources) + (1 if music_source is not None else 0)
    )
    project_id = str(context["job"]["project_id"])
    job_id = str(context["job"]["id"])
    output_directory = settings.media_root / "deliveries" / project_id / job_id / f"v{version}"
    if delivery_slug:
        output_directory = output_directory / "variants" / delivery_slug
    width, height = _delivery_dimensions(str(context["job"].get("output_aspect") or "vertical"))
    captions_ass_path = output_directory / "captions.ass"
    captions_vtt_path = output_directory / "captions.vtt"
    video_path = output_directory / "final.mp4"
    cover_path = output_directory / "cover.jpg"
    post_copy_path = output_directory / "post-copy.txt"
    package_path = output_directory / "delivery.zip"
    manifest_path = output_directory / "manifest.json"

    events = adjust_caption_timing(
        caption_events(plan, context["assets"], caption_corrections),
        float(plan.caption_timing_offset_seconds),
    )
    _atomic_text(
        captions_ass_path,
        render_ass(
            events,
            width=width,
            height=height,
            brand_kit=context.get("brand_kit"),
            position=plan.caption_position,
            target_platform=str(context["job"].get("target_platform") or "all_social"),
        ),
    )
    _atomic_text(captions_vtt_path, render_webvtt(events))
    encoder = _render_video(
        sources,
        plan,
        captions_ass_path,
        video_path,
        settings.analysis_command_timeout_seconds,
        width=width,
        height=height,
        frames_per_second=FINAL_FPS,
        final_quality=True,
        music_source=music_source,
        effect_sources=effect_sources,
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
    if video_stream.get("width") != width or video_stream.get("height") != height:
        raise RuntimeError("final delivery QA found an unexpected frame size")

    duration = float(technical_probe.get("format", {}).get("duration_seconds") or 0)
    cover_seek = min(float(context["job"].get("cover_time_seconds") or 0), max(0.0, duration - 0.05))
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
        "revision_report": context.get("revision_report"),
        "creative_direction": {
            "target_duration_seconds": context["job"].get("target_duration_seconds"),
            "edit_style": context["job"].get("edit_style"),
            "music_mode": context["job"].get("music_mode"),
            "selected_music_track_id": context["job"].get("selected_music_track_id"),
            "effect_level": context["job"].get("effect_level"),
            "target_platform": context["job"].get("target_platform"),
            "must_include": context["job"].get("must_include"),
            "audience": context["job"].get("audience"),
            "story_goal": context["job"].get("story_goal"),
            "desired_feeling": context["job"].get("desired_feeling"),
            "ending_instruction": context["job"].get("ending_instruction"),
            "cover_time_seconds": context["job"].get("cover_time_seconds"),
        },
        "story_assessment": context.get("story_spine", {}).get("engagement_assessment", {}),
        "music": music_metadata,
        "creative_effects": public_effect_manifest(effect_sources),
        "brand_kit": context.get("brand_kit"),
        "tools": {
            "gm_studio_core": "0.1.0",
            "ffmpeg": _ffmpeg_version(settings.analysis_command_timeout_seconds),
            "render_template": "talking_head_adaptive_v2",
        },
        "render": {
            "width": width,
            "height": height,
            "frames_per_second": FINAL_FPS,
            "video_encoder": encoder,
            "audio_preset": "spoken_voice_v1",
            "caption_style": "clean_blue_v1",
            "color_pipeline": "transfer_aware_hdr_to_bt709_sdr_v2",
        },
        "caption_corrections": caption_corrections,
        "captions": {
            "style": "clean_blue_v1",
            "events": len(events),
            "position": plan.caption_position,
            "timing_offset_seconds": plan.caption_timing_offset_seconds,
            "platform_safe": True,
        },
        "sources": [
            {
                "asset_id": str(clip.asset_id),
                "sha256": inventory[str(clip.asset_id)].get("sha256"),
                "source_in": clip.source_in,
                "source_out": clip.source_out,
                "transition": clip.transition,
                "visual_preset": clip.visual_preset,
                "story_role": clip.story_role,
                "editorial_intent": clip.editorial_intent,
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
            "source_derived_only": music_metadata is None and not effect_sources,
            "approved_library_music": music_metadata is not None,
            "approved_library_effects": bool(effect_sources),
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }
    if plan.post_copy:
        manifest["output_sha256"]["post_copy"] = _file_sha256(post_copy_path)
    if variant_metadata is not None:
        manifest["delivery_variant"] = variant_metadata
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
