"""Mandatory technical checks before a rendered file replaces its destination."""

import math
import json
from pathlib import Path
from typing import Any
from app.media_analysis import run_command


RENDER_TIMING_VERSION = "frame_sample_clocks_v4"


def normalize_render_audio(graph: str) -> str:
    """One output contract after loudness, mixing, effects and picture layers.

    Loudnorm can raise the sample rate to 192kHz. Reset to a continuous 48kHz
    sample clock after all optional filters, not just selected cleanup paths.
    Existing silence is retained as samples; no speech is removed or stretched.
    """
    return graph.replace("[aout]", "[render_audio_input]") + (
        ";[render_audio_input]aresample=48000,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        "asettb=1/48000,asetpts=N/SR/TB[aout]"
    )


def render_timing_error(probe: dict[str, Any], expected_duration: float) -> str | None:
    """Check each track, never infer picture coverage from the MP4 duration.

    A muxer can successfully write a file with a full audio track and only half
    its video. Players then hold the last picture until the audio finishes.
    Frame rounding and AAC encoder delay are allowed; missing seconds are not.
    """
    durations = {}
    tolerance = 0.15
    for kind in ("video", "audio"):
        stream = next((s for s in probe.get("streams", []) if s.get("type") == kind), {})
        value = stream.get("duration_seconds")
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            return f"render timing QA could not read {kind} stream duration"
        durations[kind] = float(value)
        if abs(value - expected_duration) > tolerance:
            return f"{kind} is {value:.3f}s; expected {expected_duration:.3f}s"
        start = stream.get("start_seconds", 0)
        if not isinstance(start, (int, float)) or not math.isfinite(start) or abs(start) > tolerance:
            return f"{kind} stream does not start at the beginning of the edit"
    difference = abs(durations["video"] - durations["audio"])
    if difference > tolerance:
        return f"audio/video differ by {difference:.3f}s"
    return None


def aac_packet_error(payload: dict[str, Any]) -> str | None:
    """Our AAC-LC exports use 1024 samples per packet, including priming.

    Container duration can look correct when a muxer squeezes several frames
    into one-sample timestamps. Only the final packet may have a shorter span.
    This checks the encoded clock, not the intelligibility of recorded words.
    """
    streams = payload.get("streams") or []
    try:
        rate = int(streams[0]["sample_rate"])
        if streams[0].get("codec_name") != "aac" or rate <= 0:
            raise ValueError
        packets = payload["packets"]
        if not packets:
            raise ValueError
        step, tolerance = 1024 / rate, 2 / rate
        previous = None
        for index, packet in enumerate(packets):
            pts, duration = float(packet["pts_time"]), float(packet["duration_time"])
            if not math.isfinite(pts + duration) or duration <= 0:
                raise ValueError
            if previous is not None and abs(pts - previous - step) > tolerance:
                return "audio packet timestamps do not follow the encoded sample clock"
            if duration > step + tolerance or (index < len(packets) - 1 and abs(duration - step) > tolerance):
                return "audio packets contain compressed or stretched sample timing"
            previous = pts
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        return "audio packet timing QA could not read a valid AAC sample clock"
    return None


def rendered_audio_packet_error(path: Path, timeout: int) -> str | None:
    try:
        result = run_command([
            "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
            "stream=codec_name,sample_rate:packet=pts_time,duration_time", "-of", "json", str(path)
        ], timeout=timeout)
        return aac_packet_error(json.loads(result.stdout))
    except (RuntimeError, ValueError, OSError):
        return "audio packet timing QA could not inspect the encoded file"
