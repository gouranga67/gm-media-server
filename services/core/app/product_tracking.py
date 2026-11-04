"""Explicit, bounded source-region follow. No product recognition or model calls.

Uses the owner's first-frame rectangle as a fixed appearance template. Rotation,
scale changes, occlusion or ambiguous matches decline the entire shot, never
reacquire a guessed object or extend a stale path across a lost target.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from app.finishing_tools import ProductProfile, ProductTrack

VERSION = "selected_product_v1"
MAX_CLIPS, MAX_SECONDS, FPS, BUDGET_SECONDS = 2, 8, 8, 12


def clip_choices(document):
    from app.stabilization import clip_choices as shot_choices
    choices = shot_choices(document)
    tools = document.get("finishing") or {}
    for choice in choices:
        if tools.get("smart_framing", "off") != "off":
            choice.update(eligible=False, note="Turn off single-face follow before marking a product.")
        elif choice["clip_index"] in tools.get("stabilize_clips", []):
            choice.update(eligible=False, note="Clear camera-shake reduction on this shot first.")
        elif not choice["eligible"]:
            choice["note"] = choice["note"].replace("camera-shake reduction", "product tracking")
    return choices


def seed_value(value):
    return {key: getattr(value, key) for key in ProductTrack.model_fields}


def validate_product_tracking(plan):
    tools = plan.finishing
    if not tools:
        return
    seeds = {s.clip_index: s for s in tools.product_tracks}
    if len(seeds) != len(tools.product_tracks):
        raise ValueError("select each product shot only once")
    choices = {c["clip_index"]: c for c in clip_choices(plan.model_dump(mode="json"))}
    for index in seeds:
        if index not in choices or not choices[index]["eligible"]:
            raise ValueError(f"Product shot {index + 1}: " + choices.get(index, {}).get("note", "select an existing clip"))
    seen = set()
    for profile in tools.product_profiles:
        index = profile.clip_index
        if index in seen or index not in seeds or seed_value(profile) != seed_value(seeds[index]):
            raise ValueError("product measurement belongs to a different selection")
        seen.add(index)
        clip = plan.clips[index]
        if profile.asset_id != clip.asset_id or abs(profile.source_in - clip.source_in) > .001 or abs(profile.source_out - clip.source_out) > .001:
            raise ValueError("product measurement belongs to a different source range")


def decoder(source, start, duration, *, one_frame=False):
    """Shared first frame and tracking geometry; original HDR/rotation preserved."""
    from app.media_analysis import probe_media, video_probe_hdr_mode, hdr_to_sdr_filter
    probe = probe_media(Path(source), 3)
    video = next(s for s in probe["streams"] if s.get("type") == "video")
    width, height = int(video["width"]), int(video["height"])
    if abs(video.get("rotation_degrees") or 0) % 180 == 90:
        width, height = height, width
    scale = min(1, 480 / max(width, height))
    sw, sh = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
    mode = video_probe_hdr_mode(probe)
    normalise = hdr_to_sdr_filter(mode) + "," if mode else ""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-map", "0:v:0", "-an", "-sn", "-dn", "-vf",
        f"{normalise}fps={FPS}:start_time=0,scale={sw}:{sh},setsar=1",
        "-frames:v", "1" if one_frame else str(math.ceil(duration * FPS)), "-filter_threads", "1"]
    return command, (width, height), (sw, sh)


def first_frame(source, start, duration):
    command, _, _ = decoder(source, start, duration, one_frame=True)
    result = subprocess.run(command + ["-c:v", "mjpeg", "-q:v", "3", "-f", "image2pipe", "pipe:1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
    if not result.stdout or len(result.stdout) > 1024 * 1024:
        raise ValueError("the selected shot's first frame is unavailable")
    return result.stdout


def track_frames(frames, seed):
    """Conservative translation-only template tracking at 8 fps, small frames."""
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    height, width = frames[0].shape
    bw, bh = round(seed.width * width), round(seed.height * height)
    left, top = round(seed.x * width - bw / 2), round(seed.y * height - bh / 2)
    if min(bw, bh) < 12 or left < 0 or top < 0 or left + bw > width or top + bh > height:
        raise ValueError("Selection is too small to follow; mark a larger detailed region.")
    template = frames[0][top:top + bh, left:left + bw].copy()
    if float(np.std(template)) < 12:
        raise ValueError("Selection lacks visual detail; existing framing retained.")
    points = []
    # Search at most 8% of the source per sample; no global re-identification.
    radius = max(8, round(max(width, height) * .08))
    for i, gray in enumerate(frames):
        x0, y0 = max(0, left - radius), max(0, top - radius)
        x1, y1 = min(width, left + bw + radius), min(height, top + bh + radius)
        scores = cv2.matchTemplate(gray[y0:y1, x0:x1], template, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        # Suppress only the same match's 3-pixel neighbourhood. Nearby equal
        # products/patterns must not silently substitute for the marked item.
        alternatives = scores.copy()
        alternatives[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = -1
        if not math.isfinite(score) or score < .80 or score - float(alternatives.max()) < .04:
            raise ValueError("Target became unclear, hidden or ambiguous; existing framing retained.")
        left, top = x0 + x, y0 + y
        points.append({"time": i / FPS, "x": round((left + bw / 2) / width, 6),
            "y": round((top + bh / 2) / height, 6), "width": bw / width, "height": bh / height})
    # 4 Hz saved crop path; inspect at 8 Hz and keep the final measured sample.
    return [p for i, p in enumerate(points) if i % 2 == 0 or i == len(points) - 1]


def inspect_clip(source, start, duration, seed):
    import numpy as np
    command, dimensions, (width, height) = decoder(source, start, duration)
    result = subprocess.run(command + ["-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
    count = len(result.stdout) // (width * height)
    # The fps filter rounds the final partial interval. Require a full sample
    # grid, allowing at most 250 ms of constant final crop (never a held video).
    if not math.floor(duration * FPS) <= count <= math.ceil(duration * FPS):
        raise ValueError("Incomplete decoded shot; existing framing retained.")
    frames = np.frombuffer(result.stdout, np.uint8).reshape(count, height, width)
    return {"source_width": dimensions[0], "source_height": dimensions[1],
        "points": track_frames(frames, seed), "status": "measured",
        "note": "Marked region followed locally. Review the full shot; rotation, scale and occlusion are not repaired."}


def measure_clip(asset, clip, seed, settings, timeout):
    from app.editor_context import resolve_internal_asset_source
    source = resolve_internal_asset_source(settings, asset)
    stat = source.stat()
    binding = dict(**seed_value(seed), asset_id=clip.asset_id, source_in=clip.source_in, source_out=clip.source_out)
    identity = [VERSION, str(source), asset.get("sha256"), stat.st_size, stat.st_mtime_ns,
        {**binding, "asset_id": str(clip.asset_id)}]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = settings.media_root / "derived" / "product-tracking" / VERSION / f"{key}.json"
    try:
        cached = ProductProfile.model_validate_json(cache.read_text())
        if all(getattr(cached, k) == v for k, v in binding.items()):
            return cached
    except (OSError, ValueError):
        pass
    process = subprocess.Popen([sys.executable, "-m", "app.product_tracking", "--inspect"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        output, _ = process.communicate(json.dumps(dict(source=str(source), start=float(clip.source_in),
            duration=float(clip.source_out - clip.source_in), seed=seed_value(seed))).encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    if process.returncode:
        # Do not permanently cache a transient decoder/process failure as a
        # judgement about this target. Deliberate target-loss declines exit 0.
        raise ValueError("local tracking is temporarily unavailable")
    value = json.loads(output)
    if not isinstance(value, dict) or not set(value) <= {"source_width", "source_height", "points", "status", "note"}:
        raise ValueError("invalid local tracking measurement")
    profile = ProductProfile(**binding, **value)
    temporary = cache.with_suffix(f".{os.getpid()}.tmp")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(profile.model_dump_json())
        temporary.replace(cache)
    except OSError:
        pass
    return profile


def prepare_product_tracking(context, plan, settings=None):
    if not plan.finishing or not plan.finishing.product_tracks:
        return plan
    validate_product_tracking(plan)
    if settings is None:
        from app.config import get_settings
        settings = get_settings()
    assets = {str(a["asset_id"]): a for a in context["assets"]}
    profiles = {p.clip_index: p for p in plan.finishing.product_profiles}
    started = time.monotonic()
    for seed in plan.finishing.product_tracks:
        if seed.clip_index in profiles:
            continue  # Replay saved decisions, including a declined path.
        clip = plan.clips[seed.clip_index]
        try:
            remaining = BUDGET_SECONDS - (time.monotonic() - started)
            if remaining < .25:
                raise ValueError("inspection budget reached")
            profiles[seed.clip_index] = measure_clip(assets[str(clip.asset_id)], clip, seed, settings, min(6, remaining))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            profiles[seed.clip_index] = ProductProfile(**seed_value(seed), asset_id=clip.asset_id,
                source_in=clip.source_in, source_out=clip.source_out, status="unavailable",
                note="Local tracking unavailable or budget reached; existing framing retained.")
    return plan.model_copy(update={"finishing": plan.finishing.model_copy(update={
        "product_profiles": sorted(profiles.values(), key=lambda p: p.clip_index)}, deep=True)}, deep=True)


def crop_filter(plan, index, width, height):
    if not plan.finishing or not plan.finishing.product_tracks:
        return ""
    validate_product_tracking(plan)
    profile = next((p for p in plan.finishing.product_profiles if p.clip_index == index and p.status == "measured"), None)
    if not profile:
        return ""
    from app.visual_finishing import _crop_fits, tracked_crop
    if not _crop_fits([p.model_dump() for p in profile.points], profile.source_width, profile.source_height,
        width / height, anchor=.5):
        return ""
    return tracked_crop(profile, width, height, anchor=.5)


def tracking_manifest(plan, width, height):
    tools = plan.finishing
    return {"version": VERSION, "method": "marked_region_template_translation", "hosted_model_calls": 0,
        "max_clips": MAX_CLIPS, "max_clip_seconds": MAX_SECONDS, "inspection_budget_seconds": BUDGET_SECONDS,
        "semantic_recognition": False, "quality_verified": False,
        "selections": [s.model_dump() for s in tools.product_tracks] if tools else [],
        "profiles": [{**p.model_dump(mode="json"), "framing_applied": bool(crop_filter(plan, p.clip_index, width, height)),
            "note": p.note + (" Target cannot safely fit this aspect and existing zoom; framing retained."
                if p.points and not crop_filter(plan, p.clip_index, width, height) else "")}
            for p in tools.product_profiles] if tools else []}


if __name__ == "__main__":
    if sys.argv[1:] != ["--inspect"]:
        raise SystemExit(2)
    payload = json.loads(sys.stdin.read(8192))
    if not 0 <= payload["start"] <= 86400 or not 1 <= payload["duration"] <= MAX_SECONDS:
        raise SystemExit(2)
    try:
        output = inspect_clip(payload["source"], payload["start"], payload["duration"], ProductTrack(**payload["seed"]))
    except ValueError as error:
        output = {"status": "unavailable", "note": str(error)[:400]}
    print(json.dumps(output, allow_nan=False))
