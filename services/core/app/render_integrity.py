"""Mandatory technical checks before a rendered file replaces its destination."""

import math
from typing import Any


RENDER_TIMING_VERSION = "frame_sample_clocks_v3"


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
