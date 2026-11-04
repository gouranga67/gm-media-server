"""Bounded selected-shot measurements; no identity recognition or hosted calls.

The small YuNet face detector is a framing hint, not product detection. Sampled
single-face tracks are accepted only with strong coverage and continuity. All
decisions are frozen into the edit plan before a render starts.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time

from app.finishing_tools import FinishingTools, VisualProfile

VERSION = "selected_visual_v1"
MAX_CLIPS = 8
MAX_SECONDS = 12
MAX_FRAMES = 24
BUDGET_SECONDS = 20
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MODEL_PATH = "/models/face_detection_yunet_2023mar.onnx"


def inspect_clip(source, start, duration, proxy=None, model_path=None):
    """Runs in an interruptible child. Decode at most 24 small square frames."""
    import cv2
    import numpy as np
    from app.media_analysis import probe_media, video_probe_hdr_mode, hdr_to_sdr_filter

    cv2.setNumThreads(1)
    model = Path(model_path or os.environ.get("VISUAL_FRAMING_MODEL_PATH", MODEL_PATH))
    if model.stat().st_size != 232589 or hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("framing model does not match its pinned revision")
    detector = cv2.FaceDetectorYN.create(str(model), "", (480, 480), .9, .3, 32)
    probe = probe_media(Path(source), 3)
    if not video_probe_hdr_mode(probe) and proxy:
        source = proxy
        probe = probe_media(Path(source), 3)
    stream = next(s for s in probe["streams"] if s.get("type") == "video")
    width, height = int(stream["width"]), int(stream["height"])
    if abs(stream.get("rotation_degrees") or 0) % 180 == 90:
        width, height = height, width
    mode = video_probe_hdr_mode(probe)
    normalise = hdr_to_sdr_filter(mode) + "," if mode else ""
    # Padding bounds memory even for extremely tall/wide media. Coordinates are
    # converted back out of this analysis-only letterbox before saving.
    scale = min(480 / width, 480 / height)
    sw, sh = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
    xpad, ypad = (480 - sw) // 2, (480 - sh) // 2
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"{normalise}fps=2:start_time=0,scale={sw}:{sh},setsar=1,pad=480:480:{xpad}:{ypad},format=bgr24",
        "-frames:v", str(MAX_FRAMES), "-filter_threads", "1", "-f", "rawvideo", "pipe:1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
    frames = []
    count = min(MAX_FRAMES, len(result.stdout) // (480 * 480 * 3))
    for index in range(count):
        picture = np.frombuffer(result.stdout, np.uint8, count=480 * 480 * 3, offset=index * 480 * 480 * 3).reshape(480, 480, 3)
        _, detections = detector.detect(picture)
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)[ypad:ypad + sh, xpad:xpad + sw]
        faces = []
        for detection in detections if detections is not None else []:
            x, y, w, h = map(float, detection[:4])
            left, top = max(0, x - xpad), max(0, y - ypad)
            right, bottom = min(sw, x + w - xpad), min(sh, y + h - ypad)
            if right <= left or bottom <= top:
                continue
            faces.append({"x": round((left + right) / 2 / sw, 5), "y": round((top + bottom) / 2 / sh, 5),
                "width": round((right - left) / sw, 5), "height": round((bottom - top) / sh, 5)})
        frames.append({"time": index / 2, "faces": faces[:8], "luma": round(float(np.median(gray)) / 255, 5),
            "highlight": round(float(np.percentile(gray, 98)) / 255, 5)})
    return {"version": VERSION, "width": width, "height": height, "hdr": bool(mode), "frames": frames}


def _valid(value, duration):
    try:
        if value["version"] != VERSION or not isinstance(value.get("hdr"), bool) or not 0 < value["width"] <= 32768 or not 0 < value["height"] <= 32768:
            return False
        frames = value["frames"]
        if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
            return False
        for i, frame in enumerate(frames):
            if frame["time"] != i / 2 or frame["time"] >= duration or not 0 <= frame["luma"] <= 1 or not 0 <= frame["highlight"] <= 1:
                return False
            if len(frame["faces"]) > 8:
                return False
            from app.finishing_tools import FacePoint
            for face in frame["faces"]:
                FacePoint(time=frame["time"], **face)
        return True
    except (KeyError, TypeError, ValueError):
        return False


def measure_clip(asset, clip, settings, timeout):
    from app.editor_context import resolve_internal_asset_source
    from app.media_analysis import resolve_source
    source = resolve_internal_asset_source(settings, asset)
    proxy = resolve_source(settings.media_root, asset["_proxy_key"]) if asset.get("_proxy_key") else None
    stat = source.stat()
    duration = float(clip.source_out - clip.source_in)
    proxy_stat = proxy.stat() if proxy else None
    identity = [VERSION, MODEL_SHA256, asset.get("sha256"), str(source), stat.st_size, stat.st_mtime_ns,
        str(proxy), proxy_stat.st_size if proxy_stat else 0, proxy_stat.st_mtime_ns if proxy_stat else 0, float(clip.source_in), duration]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    cache = settings.media_root / "derived" / "visual-finishing" / VERSION / f"{key}.json"
    try:
        value = json.loads(cache.read_text())
        if _valid(value, duration):
            return value
    except (OSError, ValueError):
        pass
    # Kill the process group on timeout, including its decoder. Never leave a
    # detached FFmpeg consuming the owner's CPU after the inspection budget.
    process = subprocess.Popen([sys.executable, "-m", "app.visual_finishing", "--inspect"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        output, _ = process.communicate(json.dumps({"source": str(source), "proxy": str(proxy) if proxy else None,
            "model_path": str(getattr(settings, "visual_framing_model_path", os.environ.get("VISUAL_FRAMING_MODEL_PATH", MODEL_PATH))),
            "start": float(clip.source_in), "duration": duration}).encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    if process.returncode:
        raise ValueError("local visual measurement is unavailable")
    value = json.loads(output)
    if not _valid(value, duration):
        raise ValueError("invalid visual measurement")
    temporary = cache.with_suffix(f".{os.getpid()}.tmp")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, allow_nan=False))
        temporary.replace(cache)
    except OSError:
        pass
    return value


def face_track(measured, duration):
    frames = measured["frames"]
    # No extrapolated tracking over long uninspected tails, no guessed speaker
    # selection from groups, and no re-identification after an occlusion/cut.
    if len(frames) < max(3, math.floor(duration * 2)) or any(len(f["faces"]) > 1 for f in frames):
        return [], "Group, short or incomplete shot; existing framing retained."
    detected = [f for f in frames if len(f["faces"]) == 1]
    if len(detected) / len(frames) < .85 or not detected or detected[0]["time"] > .5 or frames[-1]["time"] - detected[-1]["time"] > .5:
        return [], "Face coverage is uncertain; existing framing retained."
    points = [{"time": f["time"], **f["faces"][0]} for f in detected]
    for a, b in zip(points, points[1:]):
        gap = b["time"] - a["time"]
        if gap > 1 or math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / gap > .25 or not .67 < b["width"] / a["width"] < 1.5:
            return [], "Abrupt subject or shot change; existing framing retained."
    # A three-sample median rejects detector jitter. The crop fit check below
    # still uses each measured box to reject unsafe offsets after smoothing.
    result = []
    for i, point in enumerate(points):
        neighbors = points[max(0, i - 1):min(len(points), i + 2)]
        result.append({**point, "x": round(statistics.median(p["x"] for p in neighbors), 5),
            "y": round(statistics.median(p["y"] for p in neighbors), 5)})
    # Store conservative enclosing boxes around the smoothed centres.
    for point, raw in zip(result, points):
        point["width"] = round(raw["width"] + 2 * abs(raw["x"] - point["x"]), 5)
        point["height"] = round(raw["height"] + 2 * abs(raw["y"] - point["y"]), 5)
    from app.finishing_tools import FacePoint
    try:
        for point in result:
            FacePoint(**point)
    except ValueError:
        return [], "Subject is too close to a source edge; existing framing retained."
    return result, "Sparse single-face follow; review motion and product visibility in playback."


def _crop_fits(points, sw, sh, aspect, zoom=1.18):
    cw, ch = min(sw, sh * aspect), min(sh, sw / aspect)
    # Reserve the existing punch-in's maximum and some room around the face.
    for point in points:
        cx, cy = point["x"] * sw, point["y"] * sh
        left = max(0, min(sw - cw, cx - cw / 2))
        top = max(0, min(sh - ch, cy - ch * .38))
        mx, my = cw * (1 - 1 / zoom) / 2 + cw * .04, ch * (1 - 1 / zoom) / 2 + ch * .04
        if cx - point["width"] * sw / 2 < left + mx or cx + point["width"] * sw / 2 > left + cw - mx or cy - point["height"] * sh / 2 < top + my or cy + point["height"] * sh / 2 > top + ch - my:
            return False
    return True


def prepare_visual_finishing(context, plan, settings=None):
    tools = plan.finishing
    if not tools or (tools.smart_framing == "off" and not tools.shot_match) or tools.visual_profiles:
        return plan
    if settings is None:
        from app.config import get_settings
        settings = get_settings()
    assets = {str(a["asset_id"]): a for a in context.get("assets", [])}
    started, attempts, measurements, profiles = time.monotonic(), 0, {}, []
    for index, clip in enumerate(plan.clips):
        data = dict(clip_index=index, asset_id=clip.asset_id, source_in=clip.source_in, source_out=clip.source_out)
        duration = float(clip.source_out - clip.source_in)
        if getattr(clip, "media_kind", "video") != "video" or duration < 1.5 or duration > MAX_SECONDS:
            profiles.append(VisualProfile(**data, status="skipped", note="Inspection covers selected video shots of 1.5–12 seconds; this picture is unchanged."))
            continue
        remaining = BUDGET_SECONDS - (time.monotonic() - started)
        if attempts >= MAX_CLIPS or remaining < .25:
            profiles.append(VisualProfile(**data, status="unavailable", note="Visual inspection budget reached; picture preserved."))
            continue
        attempts += 1
        try:
            measurements[index] = measure_clip(assets[str(clip.asset_id)], clip, settings, min(5, remaining))
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            profiles.append(VisualProfile(**data, status="unavailable", note="Local visual inspection unavailable; picture preserved."))
    # Match only small SDR exposure differences. Never override manual grading,
    # infer a creative look, boost near-white highlights or undo HDR conversion.
    levels = [statistics.median(f["luma"] for f in m["frames"]) for i, m in measurements.items()
        if not m["hdr"] and len(m["frames"]) >= max(3, math.floor(float(plan.clips[i].source_out - plan.clips[i].source_in) * 2))]
    reference = statistics.median(levels) if len(levels) >= 2 else None
    aspect = {"vertical": 9 / 16, "square": 1, "landscape": 16 / 9}.get(context.get("job", {}).get("output_aspect"), 9 / 16)
    for index, measured in measurements.items():
        clip = plan.clips[index]
        points, notes = [], []
        if tools.smart_framing == "face":
            if any(m.clip_index == index for m in tools.motions):
                notes.append("Manual camera anchors take priority; automatic framing skipped.")
            else:
                points, note = face_track(measured, float(clip.source_out - clip.source_in))
                if points and not _crop_fits(points, measured["width"], measured["height"], aspect):
                    points, note = [], "Face cannot safely fit this crop and existing zoom; framing retained."
                notes.append(note)
        brightness = 0
        if tools.shot_match:
            level = statistics.median(f["luma"] for f in measured["frames"])
            highlights = max(f["highlight"] for f in measured["frames"])
            manual = any(c.clip_index == index for c in tools.colours)
            complete = len(measured["frames"]) >= max(3, math.floor(float(clip.source_out - clip.source_in) * 2))
            if complete and reference is not None and not measured["hdr"] and not manual and .08 < level < .85 and .025 < abs(reference - level) <= .12:
                brightness = round(max(-.035, min(.035, reference - level)), 4)
                if brightness > 0 and highlights > .94:
                    brightness = 0
            notes.append(f"Small exposure match {brightness:+.3f}." if brightness else "Exposure preserved (manual/HDR/uncertain or no small mismatch).")
        profiles.append(VisualProfile(clip_index=index, asset_id=clip.asset_id, source_in=clip.source_in, source_out=clip.source_out,
            status="measured", source_width=measured["width"], source_height=measured["height"], points=points,
            brightness=brightness, sampled_frames=len(measured["frames"]), note=" ".join(notes)[:400]))
    tools = tools.model_copy(update={"visual_profiles": sorted(profiles, key=lambda p: p.clip_index)}, deep=True)
    return plan.model_copy(update={"schema_version": "1.5", "finishing": tools}, deep=True)


def source_crop_filter(plan, index, width, height):
    """Replace only the first centre-fill crop; never touch frame/audio clocks."""
    tools = plan.finishing
    if not tools or tools.smart_framing != "face" or any(m.clip_index == index for m in tools.motions):
        return ""
    profile = next((p for p in tools.visual_profiles if p.clip_index == index and p.status == "measured" and p.points), None)
    if not profile:
        return ""
    points = [p.model_dump() for p in profile.points]
    if not _crop_fits(points, profile.source_width, profile.source_height, width / height):
        return ""  # Delivery variants may use a tighter aspect than the preview.

    def curve(field):
        expression = f"{getattr(profile.points[-1], field):.5f}"
        for a, b in reversed(list(zip(profile.points, profile.points[1:]))):
            av, bv = getattr(a, field), getattr(b, field)
            part = f"{av:.5f}+({bv - av:.5f})*max(0,min(1,(t-{a.time:.3f})/{b.time - a.time:.3f}))"
            expression = f"if(lt(t,{b.time:.3f}),{part},{expression})"
        return expression

    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:x='max(0,min(iw-ow,iw*({curve('x')})-ow/2))':"
        f"y='max(0,min(ih-oh,ih*({curve('y')})-oh*.38))'")


def visual_manifest(plan, aspect="vertical"):
    from app.stabilization import stabilization_manifest
    tools = plan.finishing
    width, height = {"vertical": (540, 960), "square": (540, 540), "landscape": (960, 540)}.get(aspect, (540, 960))
    profiles = []
    for p in tools.visual_profiles if tools else []:
        applied = bool(source_crop_filter(plan, p.clip_index, width, height))
        note = p.note
        if p.points and not applied:
            note += " Saved face path is not used for this aspect or manual camera choice."
        profiles.append({**p.model_dump(mode="json"), "framing_applied": applied, "note": note})
    return {"version": VERSION, "smart_framing": tools.smart_framing if tools else "off", "shot_match": bool(tools and tools.shot_match),
        "stabilize_clips": list(tools.stabilize_clips) if tools else [], "stabilization": stabilization_manifest(plan),
        "detector": "yunet_2023mar", "detector_sha256": MODEL_SHA256,
        "safe_overlays": bool(tools and tools.safe_overlays),
        "profiles": profiles,
        "hosted_model_calls": 0, "sampled_not_continuous": True, "identity_recognition": False}


if __name__ == "__main__":
    if sys.argv[1:] != ["--inspect"]:
        raise SystemExit(2)
    payload = json.loads(sys.stdin.read(8192))
    if not 0 <= payload["start"] <= 86400 or not 1.5 <= payload["duration"] <= MAX_SECONDS:
        raise SystemExit(2)
    print(json.dumps(inspect_clip(payload["source"], payload["start"], payload["duration"], payload.get("proxy"), payload.get("model_path")), allow_nan=False))
