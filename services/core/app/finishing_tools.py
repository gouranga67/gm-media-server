"""Typed, bounded local finishing instructions. No arbitrary expressions or URLs."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TimeWindow(ToolModel):
    start: float = Field(ge=0, le=60)
    end: float = Field(gt=0, le=60)

    @model_validator(mode="after")
    def forward(self):
        if self.end <= self.start:
            raise ValueError("a finishing range must move forward")
        return self


class MotionPoint(ToolModel):
    time: float = Field(ge=0, le=60)
    zoom: float = Field(default=1.0, ge=1, le=1.35)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)


class ClipMotion(ToolModel):
    clip_index: int = Field(ge=0, le=47)
    points: list[MotionPoint] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def ordered(self):
        if self.points[0].time != 0 or any(
            b.time <= a.time for a, b in zip(self.points, self.points[1:])
        ):
            raise ValueError("motion points must start at zero and advance in time")
        return self


class AudioRegion(TimeWindow):
    gain_db: float = Field(ge=-12, le=12)


class CaptionRegion(TimeWindow):
    position: Literal["lower_safe", "middle", "upper", "hidden"] = "lower_safe"


class ClipColour(ToolModel):
    clip_index: int = Field(ge=0, le=47)
    contrast: float = Field(default=1, ge=0.8, le=1.2)
    saturation: float = Field(default=1, ge=0.5, le=1.5)
    brightness: float = Field(default=0, ge=-0.08, le=0.08)
    gamma: float = Field(default=1, ge=0.8, le=1.2)


class PictureLayer(TimeWindow):
    asset_id: UUID
    media_kind: Literal["image", "video"]
    source_in: float = Field(default=0, ge=0, le=86400)
    width: float = Field(default=0.4, ge=0.1, le=1)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.35, ge=0, le=1)
    opacity: float = Field(default=1, ge=0.1, le=1)
    shape: Literal["rectangle", "circle"] = "rectangle"
    animation: Literal["none", "fade", "slide_up"] = "fade"
    chroma_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    chroma_similarity: float = Field(default=0.12, ge=0.01, le=0.4)
    chroma_blend: float = Field(default=0.08, ge=0, le=0.3)
    playback_rate: float = Field(default=1, ge=0.25, le=4)
    freeze: bool = False


class AudioJoin(ToolModel):
    clip_index: int = Field(ge=0, le=47)
    lead_seconds: float = Field(default=0, ge=0, le=1)
    tail_seconds: float = Field(default=0, ge=0, le=1)


class FinishingTools(ToolModel):
    motions: list[ClipMotion] = Field(default_factory=list, max_length=24)
    audio_regions: list[AudioRegion] = Field(default_factory=list, max_length=40)
    caption_regions: list[CaptionRegion] = Field(default_factory=list, max_length=40)
    colours: list[ClipColour] = Field(default_factory=list, max_length=24)
    layers: list[PictureLayer] = Field(default_factory=list, max_length=4)
    music_start_seconds: float = Field(default=0, ge=0, le=86400)
    voice_denoise: bool = False
    audio_joins: list[AudioJoin] = Field(default_factory=list, max_length=8)


def validate_finishing(
    plan: Any,
    assets: list[dict[str, Any]],
    music_tracks: list[dict[str, Any]] | None = None,
) -> None:
    tools = plan.finishing
    if tools is None:
        return
    if tools.music_start_seconds:
        track = next(
            (
                track
                for track in music_tracks or []
                if str(track.get("track_id") or track.get("id"))
                == str(plan.music_track_id)
            ),
            None,
        )
        if (
            not track
            or plan.music_mix == "none"
            or tools.music_start_seconds >= float(track.get("duration_seconds", 0))
        ):
            raise ValueError(
                "music excerpt must start inside the selected licensed track"
            )
    durations = [
        float(c.duration if hasattr(c, "duration") else c.source_out - c.source_in)
        for c in plan.clips
    ]
    total = sum(durations)
    for name in ("motions", "colours"):
        items = getattr(tools, name)
        indexes = [item.clip_index for item in items]
        if len(indexes) != len(set(indexes)) or any(
            index >= len(durations) for index in indexes
        ):
            raise ValueError(f"{name} must identify distinct existing clips")
    for motion in tools.motions:
        if motion.points[-1].time > durations[motion.clip_index] + 0.01:
            raise ValueError("camera move extends beyond its clip")
    for name in ("audio_regions", "caption_regions"):
        previous = 0.0
        for region in sorted(getattr(tools, name), key=lambda item: item.start):
            if region.start < previous - 0.001 or region.end > total + 0.01:
                raise ValueError(f"{name} cannot overlap or extend beyond this edit")
            previous = region.end
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    join_indexes = [j.clip_index for j in tools.audio_joins]
    if len(join_indexes) != len(set(join_indexes)) or any(
        i >= len(plan.clips) for i in join_indexes
    ):
        raise ValueError("audio joins must identify distinct existing clips")
    joined_windows = sorted(
        (
            sum(durations[: j.clip_index]) - j.lead_seconds,
            sum(durations[: j.clip_index + 1]) + j.tail_seconds,
        )
        for j in tools.audio_joins
    )
    if any(a[1] > b[0] + 0.001 for a, b in zip(joined_windows, joined_windows[1:])):
        raise ValueError(
            "independent audio joins cannot overlap; use one join at that boundary"
        )
    for join in tools.audio_joins:
        clip = plan.clips[join.clip_index]
        at = sum(durations[: join.clip_index])
        duration = durations[join.clip_index]
        source = inventory.get(str(clip.asset_id), {})
        if (
            not source.get("has_audio")
            or getattr(clip, "media_kind", "video") != "video"
            or not getattr(clip, "include_source_audio", True)
        ):
            raise ValueError("independent audio joins require audible source video")
        if (
            clip.source_in < join.lead_seconds
            or clip.source_out + join.tail_seconds
            > float(source.get("duration_seconds", 0)) + 0.001
            or at < join.lead_seconds
            or at + duration + join.tail_seconds > total + 0.001
        ):
            raise ValueError("audio join extends beyond available source or reel time")
        # Prevent an incoming/outgoing voice from covering another spoken phrase.
        for other_index, other in enumerate(plan.clips):
            if other_index == join.clip_index or not getattr(
                other, "include_source_audio", True
            ):
                continue
            other_at = sum(durations[:other_index])
            other_source = inventory.get(str(other.asset_id), {})
            windows = [
                (at - join.lead_seconds, at),
                (at + duration, at + duration + join.tail_seconds),
            ]
            for segment in other_source.get("transcript_segments", []):
                words = segment.get("words") or [segment]
                for word in words:
                    a = other_at + max(0, float(word.get("start", 0)) - other.source_in)
                    b = other_at + min(
                        durations[other_index],
                        float(word.get("end", 0)) - other.source_in,
                    )
                    if b > a and any(max(a, x) < min(b, y) - 0.01 for x, y in windows):
                        raise ValueError(
                            "audio join overlaps another spoken phrase; choose a speech-free boundary"
                        )
    for layer in tools.layers:
        asset = inventory.get(str(layer.asset_id))
        if not asset:
            raise ValueError("picture layer must use a source attached to this job")
        is_image = str(asset.get("mime_type", "")).startswith("image/")
        if is_image != (layer.media_kind == "image") or (
            not is_image and not asset.get("has_video")
        ):
            raise ValueError("picture layer kind does not match its source")
        if layer.end > total + 0.01:
            raise ValueError("picture layer extends beyond this edit")
        if not is_image:
            needed = (
                0.04
                if layer.freeze
                else (layer.end - layer.start) * layer.playback_rate
            )
            if (
                layer.source_in + needed
                > float(asset.get("duration_seconds", 0)) + 0.01
            ):
                raise ValueError("picture layer exceeds available source frames")
        elif layer.source_in or layer.freeze or layer.playback_rate != 1:
            raise ValueError("still picture layers use source zero at normal speed")
        # At most two simultaneous layers on this small appliance.
    boundaries = sorted({v for layer in tools.layers for v in (layer.start, layer.end)})
    if any(
        sum(layer.start <= t < layer.end for layer in tools.layers) > 2
        for t in boundaries
    ):
        raise ValueError("at most two picture layers may overlap")


def _curve(points: list[MotionPoint], field: str, fps: int) -> str:
    expression = f"{getattr(points[-1], field):.5f}"
    for a, b in reversed(list(zip(points, points[1:]))):
        start, end = a.time * fps, b.time * fps
        lerp = f"({getattr(a, field):.5f}+({getattr(b, field) - getattr(a, field):.5f})*(on-{start:.3f})/{end - start:.3f})"
        expression = f"if(lt(on,{end:.3f}),{lerp},{expression})"
    return expression


def clip_finishing_filter(
    plan: Any, index: int, *, width: int, height: int, fps: int
) -> str:
    tools = plan.finishing
    if tools is None:
        return ""
    filters = []
    motion = next((m for m in tools.motions if m.clip_index == index), None)
    if motion:
        zoom, x, y = (_curve(motion.points, field, fps) for field in ("zoom", "x", "y"))
        filters.append(
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({x})':y='(ih-ih/zoom)*({y})':d=1:s={width}x{height}:fps={fps}"
        )
    colour = next((c for c in tools.colours if c.clip_index == index), None)
    if colour:
        filters.append(
            f"eq=contrast={colour.contrast:.4f}:brightness={colour.brightness:.4f}:saturation={colour.saturation:.4f}:gamma={colour.gamma:.4f}"
        )
    return ",".join(filters)


def voice_finishing_filter(plan: Any) -> str:
    if plan.finishing is None:
        return ""
    filters = ["afftdn=nr=10:nf=-40"] if plan.finishing.voice_denoise else []
    for region in plan.finishing.audio_regions:
        filters.append(
            f"volume={region.gain_db:.4f}dB:enable='gte(t,{region.start:.3f})*lt(t,{region.end:.3f})'"
        )
    return ",".join(filters)


def finish_caption_events(
    events: list[dict], tools: FinishingTools | None
) -> list[dict]:
    if tools is None or not tools.caption_regions:
        return events
    result = []
    for event in events:
        a, b = float(event["start"]), float(event["end"])
        boundaries = sorted(
            {
                a,
                b,
                *[
                    v
                    for region in tools.caption_regions
                    for v in (region.start, region.end)
                    if a < v < b
                ],
            }
        )
        for start, end in zip(boundaries, boundaries[1:]):
            region = next(
                (
                    r
                    for r in tools.caption_regions
                    if r.start <= (start + end) / 2 < r.end
                ),
                None,
            )
            if region and region.position == "hidden":
                continue
            result.append(
                {
                    **event,
                    "start": start,
                    "end": end,
                    **({"position": region.position} if region else {}),
                }
            )
    return result


def apply_graph_finishing(
    graph: str,
    plan: Any,
    *,
    width: int,
    height: int,
    fps: int,
    join_sources: list[dict] | None = None,
) -> str:
    if plan.finishing is None:
        return graph
    parts = graph.split(";")
    appended = []
    for index, _clip in enumerate(plan.clips):
        chain = clip_finishing_filter(plan, index, width=width, height=height, fps=fps)
        if chain:
            suffix = f"[v{index}]"
            for i, part in enumerate(parts):
                if part.endswith(suffix):
                    parts[i] = part[: -len(suffix)] + f"[toolv{index}]"
                    appended.append(f"[toolv{index}]{chain}[v{index}]")
                    break
    joins = join_sources or []
    if joins:
        parts = [
            part.replace("[acat]", "[joinedvoice]", 1)
            if part.startswith("[acat]")
            else part
            for part in parts
        ]
        mute = ",".join(
            f"volume=0:enable='gte(t,{j['start']:.3f})*lt(t,{j['start'] + j['duration']:.3f})'"
            for j in joins
        )
        appended.append(f"[acat]{mute}[joinbed]")
        labels = ["[joinbed]"]
        for index, source in enumerate(joins):
            delay = round(source["start"] * 48000)
            duration = source["duration"]
            appended.append(
                f"[{source['input_index']}:a:0]aresample=48000,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume={source.get('gain_db', 0):.3f}dB,afade=t=in:st=0:d=0.025,afade=t=out:st={max(0, duration - 0.025):.3f}:d=0.025,adelay={delay}S:all=1[join{index}]"
            )
            labels.append(f"[join{index}]")
        total = sum(
            float(c.duration if hasattr(c, "duration") else c.source_out - c.source_in)
            for c in plan.clips
        )
        appended.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:duration=first:normalize=0,atrim=duration={total:.3f}[joinedvoice]"
        )
    voice = voice_finishing_filter(plan)
    if voice:
        input_label = "joinedvoice" if joins else "acat"
        parts = [
            part.replace(f"[{input_label}]", "[toolvoice]", 1)
            if part.startswith(f"[{input_label}]")
            else part
            for part in parts
        ]
        appended.append(f"[{input_label}]{voice}[toolvoice]")
    return ";".join(parts + appended)


def selected_picture_layers(
    context: dict, plan: Any, settings: Any, first_index: int
) -> list[dict]:
    if plan.finishing is None:
        return []
    from app.editor_context import (
        resolve_internal_asset_source,
        resolve_internal_asset_render_source,
    )
    from app.media_analysis import probe_media, video_probe_hdr_mode

    inventory = {str(asset["asset_id"]): asset for asset in context["assets"]}
    result = []
    for index, layer in enumerate(plan.finishing.layers):
        asset = inventory[str(layer.asset_id)]
        path = (
            resolve_internal_asset_source
            if layer.media_kind == "image"
            else resolve_internal_asset_render_source
        )(settings, asset)
        result.append(
            {
                "cue": layer,
                "path": path,
                "input_index": first_index + index,
                "hdr_mode": video_probe_hdr_mode(
                    probe_media(path, settings.analysis_command_timeout_seconds)
                )
                if layer.media_kind == "video"
                else None,
            }
        )
    return result


def picture_layer_inputs(sources: list[dict]) -> list[str]:
    args = []
    for source in sources:
        cue = source["cue"]
        duration = cue.end - cue.start
        if cue.media_kind == "image":
            args += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(source["path"])]
        else:
            args += [
                "-ss",
                f"{cue.source_in:.3f}",
                "-t",
                f"{0.04 if cue.freeze else duration * cue.playback_rate:.3f}",
                "-i",
                str(source["path"]),
            ]
    return args


def append_picture_layers(
    graph: str, sources: list[dict], *, width: int, height: int, fps: int
) -> str:
    if not sources:
        return graph
    from app.media_analysis import hdr_to_sdr_filter

    parts = graph.split(";")
    captions = None
    for index, part in enumerate(parts):
        match = re.fullmatch(r"\[([A-Za-z0-9_]+)\](subtitles=.*)\[vout\]", part)
        if match:
            captions = match[2]
            parts[index] = f"[{match[1]}]null[vout]"
            break
    parts = [part.replace("[vout]", "[layerbase0]") for part in parts]
    for index, source in enumerate(sources):
        cue = source["cue"]
        duration = cue.end - cue.start
        pixels = max(2, int(width * cue.width) // 2 * 2)
        size = f"scale={pixels}:{pixels if cue.shape == 'circle' else -2}" + (
            ":force_original_aspect_ratio=increase,crop="
            + str(pixels)
            + ":"
            + str(pixels)
            if cue.shape == "circle"
            else ""
        )
        # Rectangle layers contain their source; constrain height for tall stills.
        if cue.shape == "rectangle":
            size = f"scale={pixels}:{max(2, int(height * 0.85) // 2 * 2)}:force_original_aspect_ratio=decrease:force_divisible_by=2"
        normalise = (
            hdr_to_sdr_filter(source["hdr_mode"]) + ","
            if source.get("hdr_mode")
            else ""
        )
        key = (
            f",chromakey=0x{cue.chroma_color[1:]}:{cue.chroma_similarity:.4f}:{cue.chroma_blend:.4f}"
            if cue.chroma_color
            else ""
        )
        chain = f"[{source['input_index']}:v:0]{normalise}setpts=(PTS-STARTPTS)/{cue.playback_rate:.4f},{size},setsar=1,fps={fps},format=yuva444p{key},format=rgba"
        if cue.shape == "circle":
            chain += ",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-W/2,2)+pow(Y-H/2,2),pow(W/2,2)),alpha(X,Y),0)'"
        chain += f",colorchannelmixer=aa={cue.opacity:.4f},tpad=stop_mode=clone:stop_duration={duration:.3f},trim=duration={duration:.3f}"
        if cue.animation == "fade":
            fade = min(0.18, duration / 4)
            chain += f",fade=t=in:st=0:d={fade:.3f}:alpha=1,fade=t=out:st={duration - fade:.3f}:d={fade:.3f}:alpha=1"
        chain += f",setpts=PTS-STARTPTS+{cue.start:.3f}/TB[layerpic{index}]"
        parts.append(chain)
        y = f"(H-h)*{cue.y:.5f}"
        if cue.animation == "slide_up":
            y += f"+min(1,max(0,({cue.start + 0.2:.3f}-t)/0.2))*H*.12"
        parts.append(
            f"[layerbase{index}][layerpic{index}]overlay=x='(W-w)*{cue.x:.5f}':y='{y}':enable='gte(t,{cue.start:.3f})*lt(t,{cue.end:.3f})':eof_action=pass:repeatlast=0[layerbase{index + 1}]"
        )
    parts.append(f"[layerbase{len(sources)}]{captions or 'null'}[vout]")
    return ";".join(parts)


def retime_finishing(
    tools: FinishingTools | None,
    mapping: list[list[float]],
    clips: list[Any],
    origins: list[tuple[int | None, float, float]],
) -> FinishingTools | None:
    """Move finishing with retained content, including repeated source occurrences."""
    if tools is None:
        return None
    if tools.audio_joins:
        raise ValueError(
            "clear independent audio joins before changing timeline lengths or source ranges"
        )
    data = tools.model_dump(mode="json")
    for name in ("audio_regions", "caption_regions", "layers"):
        result = []
        for region in data[name]:
            for old_start, old_end, new_start in mapping:
                start, end = (
                    max(region["start"], old_start),
                    min(region["end"], old_end),
                )
                if end - start < 0.02:
                    continue
                item = {
                    **region,
                    "start": round(new_start + start - old_start, 3),
                    "end": round(new_start + end - old_start, 3),
                }
                if (
                    name == "layers"
                    and item["media_kind"] == "video"
                    and not item.get("freeze")
                ):
                    item["source_in"] = round(
                        item["source_in"]
                        + (start - region["start"]) * item.get("playback_rate", 1),
                        3,
                    )
                result.append(item)
        data[name] = result
    data["motions"] = []
    data["colours"] = []

    def sample(points, at):
        if at >= points[-1].time:
            return points[-1].model_copy(update={"time": at})
        for a, b in zip(points, points[1:]):
            if a.time <= at < b.time:
                ratio = (at - a.time) / (b.time - a.time)
                return MotionPoint(
                    time=at,
                    **{
                        field: getattr(a, field)
                        + (getattr(b, field) - getattr(a, field)) * ratio
                        for field in ("zoom", "x", "y")
                    },
                )
        return points[0].model_copy(update={"time": at})

    for index, (old_index, offset, duration) in enumerate(origins):
        for colour in tools.colours:
            if colour.clip_index == old_index:
                data["colours"].append({**colour.model_dump(), "clip_index": index})
        for motion in tools.motions:
            if motion.clip_index == old_index:
                start = max(0, offset)
                end = max(start + 0.001, offset + duration)
                points = [
                    sample(motion.points, start),
                    *[p for p in motion.points if start < p.time < end],
                    sample(motion.points, end),
                ]
                data["motions"].append(
                    {
                        "clip_index": index,
                        "points": [
                            {**p.model_dump(), "time": round(p.time - start, 3)}
                            for p in points
                        ],
                    }
                )
    try:
        return FinishingTools.model_validate(data)
    except ValueError as error:
        raise ValueError(
            "this timeline change would exceed finishing bounds; clear local finishing or make a smaller change"
        ) from error


def audio_join_sources(plan: Any, paths: list[Any], first_index: int) -> list[dict]:
    if plan.finishing is None:
        return []
    durations = [
        float(c.duration if hasattr(c, "duration") else c.source_out - c.source_in)
        for c in plan.clips
    ]
    result = []
    for index, join in enumerate(plan.finishing.audio_joins):
        clip = plan.clips[join.clip_index]
        at = sum(durations[: join.clip_index])
        duration = durations[join.clip_index]
        result.append(
            {
                "path": paths[join.clip_index],
                "input_index": first_index + index,
                "source_in": float(clip.source_in) - join.lead_seconds,
                "duration": duration + join.lead_seconds + join.tail_seconds,
                "start": at - join.lead_seconds,
                "picture_start": at,
                "picture_end": at + duration,
                "gain_db": -8.0 + float(getattr(clip, "source_audio_gain_db", 0))
                if hasattr(clip, "duration")
                else 0.0,
            }
        )
    return result


def audio_join_inputs(sources: list[dict]) -> list[str]:
    result = []
    for source in sources:
        result += [
            "-ss",
            f"{source['source_in']:.3f}",
            "-t",
            f"{source['duration']:.3f}",
            "-i",
            str(source["path"]),
        ]
    return result


def clip_audio_window(
    plan: Any, index: int, timeline: float
) -> tuple[float, float, float]:
    clip = plan.clips[index]
    join = (
        next((j for j in plan.finishing.audio_joins if j.clip_index == index), None)
        if plan.finishing
        else None
    )
    return (
        float(clip.source_in) - (join.lead_seconds if join else 0),
        float(clip.source_out) + (join.tail_seconds if join else 0),
        timeline - (join.lead_seconds if join else 0),
    )


def assemble_clip_graph(plan: Any, concat_inputs: list[str], fps: int) -> str:
    """Optional picture dissolves preserve the exact existing dialogue timeline."""
    if not any(clip.transition == "cross_dissolve" for clip in plan.clips):
        return (
            "".join(concat_inputs) + f"concat=n={len(plan.clips)}:v=1:a=1[vcat][acat]"
        )
    durations = [
        float(c.duration if hasattr(c, "duration") else c.source_out - c.source_in)
        for c in plan.clips
    ]
    parts = [
        f"[v{index}]fps={fps},settb=AVTB[xfv{index}]"
        for index in range(len(plan.clips))
    ]
    current = "xfv0"
    elapsed = durations[0]
    for index, clip in enumerate(plan.clips[1:], 1):
        target = f"joinedpicture{index}"
        if clip.transition == "cross_dissolve":
            fade = min(0.2, durations[index] / 4, durations[index - 1] / 4)
            parts.append(
                f"[{current}]tpad=stop_mode=clone:stop_duration={fade:.3f}[padpicture{index}]"
            )
            parts.append(
                f"[padpicture{index}][xfv{index}]xfade=transition=fade:duration={fade:.3f}:offset={elapsed:.3f}[{target}]"
            )
        else:
            parts.append(f"[{current}][xfv{index}]concat=n=2:v=1:a=0[{target}]")
        current = target
        elapsed += durations[index]
    parts.append(f"[{current}]trim=duration={elapsed:.3f},setpts=PTS-STARTPTS[vcat]")
    parts.append(
        "".join(f"[a{i}]" for i in range(len(plan.clips)))
        + f"concat=n={len(plan.clips)}:v=0:a=1[acat]"
    )
    return ";".join(parts)
