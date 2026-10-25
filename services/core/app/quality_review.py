"""Bounded local inspection of a rendered reel; never rewrites its edit plan."""

import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.edit_plan import EditPlan, MontageEditPlan, edit_plan_duration, source_word_gaps
from app.media_analysis import LOUDNESS_JSON_PATTERN, probe_media, run_command, video_probe_hdr_mode


QUALITY_REVIEW_VERSION = "1.0"
MAX_REVIEW_SECONDS = 61
REVIEW_TIMEOUT_SECONDS = 30


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def parse_render_measurements(stderr: str, duration: float) -> dict[str, Any]:
    """Read FFmpeg's measurements, closing trailing silence at the file end."""
    silences = []
    silence_start = None
    for match in re.finditer(r"silence_(start|end):\s*(-?[\d.]+)", stderr):
        value = _finite(match[2])
        if value is None:
            continue
        if match[1] == "start":
            silence_start = max(0.0, value)
        elif silence_start is not None:
            silences.append({"start": silence_start, "end": min(duration, value)})
            silence_start = None
    if silence_start is not None and silence_start < duration:
        silences.append({"start": silence_start, "end": duration})
    black = []
    for match in re.finditer(r"black_start:([\d.]+)\s+black_end:([\d.]+)", stderr):
        start, end = _finite(match[1]), _finite(match[2])
        if start is not None and end is not None and end > start:
            black.append({"start": start, "end": min(duration, end)})
    loudness = {}
    matches = LOUDNESS_JSON_PATTERN.findall(stderr)
    if matches:
        try:
            raw = json.loads(matches[-1])
            for name, key in (("integrated_lufs", "input_i"), ("true_peak_dbfs", "input_tp")):
                value = _finite(raw.get(key))
                if value is not None:
                    loudness[name] = value
        except (ValueError, TypeError):
            pass
    return {"silence_intervals": silences, "dark_intervals": black, "loudness": loudness}


def _review_rendered_video(
    context: dict[str, Any],
    plan: EditPlan,
    video_path: Path,
    captions: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    timeout: int = REVIEW_TIMEOUT_SECONDS,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect the actual file plus source/caption timing, with no model calls.

    Incomplete measurements are explicit and never discard a successful render.
    Timing hints are suggestions, not proof that laughter or a pause is unwanted.
    """
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    expected = edit_plan_duration(plan)
    measurements: dict[str, Any] = {}

    def check(code: str, label: str, status: str, detail: str) -> None:
        checks.append({"code": code, "label": label, "status": status, "detail": detail})

    def finding(code: str, title: str, detail: str, *, severity: str = "review", **location: Any) -> None:
        findings.append({"code": code, "title": title, "detail": detail, "severity": severity, **location})

    inventory = {str(asset["asset_id"]): asset for asset in context.get("assets", [])}
    spoken_ranges = []
    has_spoken_text = False
    timeline = 0.0
    for index, clip in enumerate(plan.clips):
        duration = float(clip.duration) if isinstance(plan, MontageEditPlan) else float(clip.source_out - clip.source_in)
        audible = not isinstance(plan, MontageEditPlan) or (clip.media_kind == "video" and clip.include_source_audio)
        if audible:
            spoken_ranges.append((timeline, timeline + duration, index))
            asset = inventory.get(str(clip.asset_id), {})
            for start, end, length in source_word_gaps(asset, float(clip.source_in), float(clip.source_out)):
                if length >= 1.5:
                    finding("source_speech_gap", "Review a gap between spoken words",
                            "Word timing shows a pause of at least 1.5s. This is not verified silence: laughter, gestures, or a deliberate reaction may belong here.",
                            clip_index=index, start_seconds=round(timeline + start - clip.source_in, 3),
                            end_seconds=round(timeline + end - clip.source_in, 3))
            clipped_words = []
            for segment in asset.get("transcript_segments", []):
                segment_start, segment_end = _finite(segment.get("start")), _finite(segment.get("end"))
                if segment_start is not None and segment_end is not None and segment.get("text") and (
                    min(segment_end, clip.source_out) - max(segment_start, clip.source_in) >= 0.08
                ):
                    has_spoken_text = True
                for word in segment.get("words", []):
                    start, end = _finite(word.get("start")), _finite(word.get("end"))
                    if start is None or end is None or end <= start:
                        continue
                    if start + 0.04 < clip.source_in < end - 0.04 or start + 0.04 < clip.source_out < end - 0.04:
                        clipped_words.append(str(word.get("text") or "").strip())
            if clipped_words:
                finding("speech_boundary", "Check a word at this cut",
                        "Source word timing crosses the cut: " + ", ".join(clipped_words[:4]) + ". Listen before changing it.",
                        clip_index=index, start_seconds=round(timeline, 3))
        timeline += duration

    caption_problem = has_spoken_text and not captions
    previous_end = 0.0
    for event in captions:
        start, end = _finite(event.get("start")), _finite(event.get("end"))
        if start is None or end is None or start < 0 or end <= start or end > expected + 0.15 or start < previous_end - 0.04:
            caption_problem = True
            break
        previous_end = end
    check("caption_schedule", "Caption schedule", "attention" if caption_problem else "passed",
          "Checks scheduled cue ranges and overlaps; does not verify burned-in text or recognition accuracy.")
    if caption_problem:
        finding("caption_schedule", "Check caption timing", "Selected speech has no scheduled captions." if has_spoken_text and not captions
                else "A scheduled caption overlaps another cue or falls outside the edit.")
    check("story_judgement", "Story and humour", "not_assessed",
          "Human review is still needed for meaning, delivery, humour, and whether an effect is appropriate.")
    music_requested = context.get("job", {}).get("music_mode") in {"subtle", "present"}
    check("music_selection", "Music selection", "passed" if not music_requested or plan.music_track_id else "attention",
          "An approved track is selected; audibility still needs listening." if plan.music_track_id
          else "No backing track selected." if music_requested else "Backing music was not requested.")
    if music_requested and not plan.music_track_id:
        finding("music_selection", "Requested music has no track", "The plan contains no backing track. Check the available music library.")

    try:
        actual = probe if probe is not None else probe_media(video_path, timeout=min(10, timeout))
        streams = actual.get("streams", [])
        video = next((stream for stream in streams if stream.get("type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("type") == "audio"), None)
        duration = _finite(actual.get("format", {}).get("duration_seconds"))
        measurements["probe"] = actual
        readable = video is not None and audio is not None
        check("streams", "Video and audio streams", "passed" if readable else "attention", "Both streams are required in the rendered file.")
        if not readable:
            finding("streams", "A media stream is missing", "The rendered file is missing video or audio.", severity="error")
        dimensions_ok = video is not None and video.get("width") == width and video.get("height") == height
        check("dimensions", "Frame size", "passed" if dimensions_ok else "attention", f"Expected {width} × {height}.")
        if not dimensions_ok:
            finding("dimensions", "Unexpected frame size", f"The rendered file does not match {width} × {height}.", severity="error")
        duration_ok = duration is not None and abs(duration - expected) <= 0.2
        check("duration", "Rendered duration", "passed" if duration_ok else "attention", f"Edit plan: {expected:.2f}s; file: {duration:.2f}s." if duration is not None else "File duration could not be read.")
        if not duration_ok:
            finding("duration", "Check the rendered duration", "The file duration does not match the selected clips.", severity="error")
        hdr = video_probe_hdr_mode(actual)
        known_sdr = bool(video and video.get("color_transfer") == "bt709")
        check("colour_metadata", "SDR colour metadata", "attention" if hdr else "passed" if known_sdr else "unavailable",
              "HDR transfer metadata remains in an SDR output." if hdr else "Transfer metadata is BT.709 SDR; visual colour accuracy still needs review." if known_sdr else "BT.709 transfer metadata could not be verified; colour appearance was not assessed.")
        if hdr:
            finding("colour_metadata", "Check HDR conversion", "The rendered output still declares an HDR transfer function.")
        bound = min(MAX_REVIEW_SECONDS, duration if duration is not None else expected)
        command = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-threads", "1", "-filter_threads", "1",
                   "-i", str(video_path), "-t", f"{bound:.3f}"]
        if video:
            command += ["-vf", "scale=160:-2,blackdetect=d=0.6:pix_th=0.05:pic_th=0.98"]
        if audio:
            command += ["-af", "silencedetect=noise=-45dB:d=1.2,loudnorm=I=-14:LRA=11:TP=-1:print_format=json"]
        command += ["-f", "null", "-"]
        result = run_command(command, timeout=min(REVIEW_TIMEOUT_SECONDS, timeout))
        measurements.update(parse_render_measurements(result.stderr, bound))
        check("decode", "Rendered-file decode", "passed", f"Decoded up to {bound:.2f}s locally.")
        check("dark_intervals", "Dark-frame scan", "passed" if video else "unavailable", "Scanned the rendered image for near-black intervals lasting at least 0.6s; these may be intentional.")
        check("quiet_intervals", "Quiet-mix scan", "passed" if audio else "unavailable", "Scanned the finished mix below −45 dB for at least 1.2s. Music can mask a dialogue pause.")
        for interval in measurements["dark_intervals"]:
            if interval["end"] - interval["start"] >= 0.6:
                finding("dark_interval", "Check a dark interval", "The rendered image is almost entirely dark here. It may be intentional.",
                        start_seconds=round(interval["start"], 3), end_seconds=round(interval["end"], 3))
        for interval in measurements["silence_intervals"]:
            if interval["end"] - interval["start"] < 1.2:
                continue
            # A quiet music-only montage section is not a dialogue defect.
            overlap = next(((start, end, index) for start, end, index in spoken_ranges
                            if min(end, interval["end"]) - max(start, interval["start"]) >= 1.2), None)
            if overlap:
                finding("quiet_interval", "Listen to a quiet stretch", "The finished mix stays below −45 dB for at least 1.2s during a source-audio clip. It may be an intentional pause.",
                        clip_index=overlap[2], start_seconds=round(interval["start"], 3), end_seconds=round(interval["end"], 3))
        loudness = measurements["loudness"]
        check("mix_loudness", "Measured mix loudness", "passed" if loudness else "unavailable",
              f"{loudness['integrated_lufs']:.1f} LUFS integrated." if "integrated_lufs" in loudness else "No finite loudness measurement was available.")
        if loudness.get("true_peak_dbfs", -100) > -0.2:
            finding("audio_peak", "Check audio peaks", "The rendered mix approaches full scale. Listen for distortion before adjusting it.")
        if loudness.get("integrated_lufs", -14) < -26 and spoken_ranges:
            finding("quiet_mix", "Check overall speech volume", "The complete mix measures below −26 LUFS. Confirm that speech is easy to hear.")
    except Exception:
        # Analysis failure is not a render failure. Never claim a pass or throw
        # away a usable preview because FFmpeg timed out or a probe was absent.
        check("render_measurement", "Rendered-file measurements", "unavailable", "Inspection could not complete within its local processing budget. The edit was preserved.")

    unavailable = any(item["status"] == "unavailable" for item in checks)
    return {
        "version": QUALITY_REVIEW_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "attention" if findings else "incomplete" if unavailable else "passed",
        "scope": "rendered_media_and_timing",
        "checks": checks,
        "findings": findings[:24],
        "finding_count": len(findings),
        "measurements": measurements,
        "hosted_model_calls": 0,
        "additional_model_tokens": 0,
        "automatic_changes": [],
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def review_rendered_video(
    context: dict[str, Any], plan: EditPlan, video_path: Path, captions: list[dict[str, Any]],
    *, width: int, height: int, timeout: int = REVIEW_TIMEOUT_SECONDS,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep optional QA failures from turning a successful render into a failure."""
    try:
        return _review_rendered_video(context, plan, video_path, captions,
            width=width, height=height, timeout=timeout, probe=probe)
    except Exception:
        return {
            "version": QUALITY_REVIEW_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "incomplete", "scope": "rendered_media_and_timing",
            "checks": [{"code": "inspection", "label": "Local inspection", "status": "unavailable",
                        "detail": "The optional inspection could not finish. Your edit was preserved."}],
            "findings": [], "finding_count": 0, "measurements": {},
            "hosted_model_calls": 0, "additional_model_tokens": 0, "automatic_changes": [],
        }
