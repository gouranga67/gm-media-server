"""Conservative, bounded CPU audio inspection. Decisions travel with the saved cut.

Quiet transcript gaps are only evidence of a possible steady noise floor, not a
measurement of true signal-to-noise ratio. Uncertain recordings are left alone.
"""

import array
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time

from app.finishing_tools import FinishingTools, VoiceCleanupProfile
from app.media_analysis import resolve_source

VERSION = "voice_cleanup_v1"
SAMPLE_RATE = 16000
MAX_SOURCES = 8
MAX_SECONDS = 18
BUDGET_SECONDS = 12


def _db(value):
    return max(-90.0, 20 * math.log10(max(value, 10 ** (-90 / 20))))


def _quantile(values, fraction):
    return sorted(values)[round((len(values) - 1) * fraction)]


def _valid_measurement(value):
    if not isinstance(value, dict) or value.get("version") != VERSION:
        return False
    for key in ("speech_dbfs", "peak_dbfs", "noise_dbfs", "speech_spread_db", "noise_spread_db", "clipped_fraction"):
        if key in value and (not isinstance(value[key], (int, float)) or not math.isfinite(value[key])):
            return False
    return "speech_dbfs" not in value or "peak_dbfs" in value


def inspect_pcm(pcm: bytes, speech_ranges: list[tuple[float, float]]) -> dict:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    speech, quiet = [], []
    size = SAMPLE_RATE // 50  # 20 ms; preserve timing, never delete audio.
    for offset in range(0, len(samples) - size + 1, size):
        at = (offset + size / 2) / SAMPLE_RATE
        frame = samples[offset:offset + size]
        level = _db(math.sqrt(sum(float(v) ** 2 for v in frame) / size) / 32768)
        if any(a <= at <= b for a, b in speech_ranges):
            speech.append(level)
        elif not any(a - 0.15 <= at <= b + 0.15 for a, b in speech_ranges):
            quiet.append(level)
    result = {"version": VERSION, "speech_frames": len(speech), "quiet_frames": len(quiet)}
    if len(speech) < 50:
        return result
    result.update(
        speech_dbfs=round(statistics.median(speech), 2),
        speech_spread_db=round(_quantile(speech, .9) - _quantile(speech, .1), 2),
        peak_dbfs=round(_db(max(abs(v) for v in samples) / 32768), 2),
        clipped_fraction=sum(abs(v) >= 32700 for v in samples) / len(samples),
    )
    if len(quiet) >= 25:
        result.update(noise_dbfs=round(statistics.median(quiet), 2),
                      noise_spread_db=round(_quantile(quiet, .9) - _quantile(quiet, .1), 2))
    return result


def choose_profile(asset_id: str, measured: dict, reference: float | None) -> VoiceCleanupProfile:
    if "speech_dbfs" not in measured or measured["speech_dbfs"] < -55:
        return VoiceCleanupProfile(asset_id=asset_id, status="skipped",
            note="Not enough measurable recorded speech; source audio preserved.")
    noise, speech = measured.get("noise_dbfs"), measured["speech_dbfs"]
    # Never infer removable noise from speech-only recordings or irregular sounds.
    reduce_noise = bool(noise is not None and -50 < noise <= -25
        and speech - noise >= 12 and measured.get("noise_spread_db", 99) <= 6)
    gain = 0
    if reference is not None and abs(reference - speech) >= 4:
        difference = reference - speech
        gain = round(min(6, difference, max(0, -3 - measured["peak_dbfs"])) if difference > 0 else max(-6, difference), 1)
    compress = bool(measured.get("speech_spread_db", 0) >= 14 and measured["peak_dbfs"] > -9)
    notes = []
    if reduce_noise:
        notes.append("Gentle steady-noise reduction and low rumble filter.")
    if gain:
        notes.append(f"Take balance {gain:+g} dB (manual levels take priority).")
    if compress:
        notes.append("Gentle peak compression for uneven speech.")
    if measured.get("clipped_fraction", 0) >= .001:
        notes.append("Source clipping detected; lost detail cannot be recovered.")
    if noise is not None and speech - noise < 12:
        notes.append("Background overlaps speech; automatic noise removal skipped.")
    return VoiceCleanupProfile(asset_id=asset_id, status="measured", noise_reduction_db=6 if reduce_noise else 0,
        noise_floor_dbfs=max(-80, min(-25, noise if noise is not None else -60)),
        balance_gain_db=gain, compress=compress,
        note=" ".join(notes)[:300] or "No cleanup needed in the inspected passage; normal output loudness processing retained.")


def _speech_ranges(asset, start, end):
    ranges = []
    for segment in asset.get("transcript_segments", []):
        # Prefer individual word timing; coarse ASR segments can include pauses.
        for item in segment.get("words") or [segment]:
            try:
                a, b = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(a + b) and a < b and a < end and b > start:
                ranges.append((max(start, a) - start, min(end, b) - start))
    return ranges


def measure_source(asset, start, end, settings, timeout):
    source = resolve_source(settings.media_root, asset["_storage_key"])
    ranges = _speech_ranges(asset, start, end)
    stat = source.stat()
    identity = [VERSION, asset.get("sha256"), str(source), stat.st_size, stat.st_mtime_ns, start, end, ranges]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = settings.media_root / "derived" / "audio-cleanup" / VERSION / f"{key}.json"
    try:
        value = json.loads(cache.read_text())
        if _valid_measurement(value):
            return value
    except (OSError, ValueError, AttributeError):
        pass
    if not ranges:
        return {"version": VERSION}
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{start:.3f}", "-t", f"{end-start:.3f}", "-i", str(source),
        "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "pipe:1"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=True)
    value = inspect_pcm(result.stdout, ranges)
    # Cache is disposable; read-only/full media storage must not break an edit.
    temporary = cache.with_suffix(f".{os.getpid()}.tmp")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, allow_nan=False))
        temporary.replace(cache)
    except OSError:
        pass
    return value


def prepare_voice_cleanup(context, plan, settings=None, *, new_edit=False):
    """Only new speech edits opt in automatically. Old versions keep their mix.

    A local finishing revision explicitly choosing Auto uses the same entry point.
    Final exports, subtitle-only versions, retries and delivery variants replay the
    stored decisions and never inspect/change an already saved plan.
    """
    from app.edit_plan import TalkingHeadEditPlan
    tools = plan.finishing or FinishingTools()
    if tools.voice_cleanup != "auto":
        brief = str(context.get("project", {}).get("brief") or "")
        if not new_edit or not isinstance(plan, TalkingHeadEditPlan) or tools.voice_denoise or re.search(
            r"\b(?:whisper\w*|ASMR|original audio|no audio cleanup|preserve.{0,30}(?:audio|volume))\b", brief, re.I):
            return plan
        tools = tools.model_copy(update={"voice_cleanup": "auto"}, deep=True)
    inventory = {str(a["asset_id"]): a for a in context.get("assets", [])}
    selected = {}
    for clip in plan.clips:
        asset_id = str(clip.asset_id)
        if hasattr(clip, "include_source_audio") and not clip.include_source_audio:
            continue
        selected.setdefault(asset_id, clip)
    measurements, profiles = {}, []
    started = time.monotonic()
    attempts = 0
    for asset_id, clip in selected.items():
        asset = inventory.get(asset_id, {})
        if not asset.get("has_audio") or not asset.get("transcript_segments"):
            profiles.append(VoiceCleanupProfile(asset_id=asset_id, status="skipped", note="No recorded speech evidence; source preserved."))
            continue
        if not asset.get("_storage_key"):
            profiles.append(VoiceCleanupProfile(asset_id=asset_id, status="unavailable", note="Source unavailable for inspection; audio preserved."))
            continue
        remaining = BUDGET_SECONDS - (time.monotonic() - started)
        if attempts >= MAX_SOURCES or remaining < .2:
            profiles.append(VoiceCleanupProfile(asset_id=asset_id, status="unavailable", note="Inspection budget reached; source preserved."))
            continue
        attempts += 1
        try:
            if settings is None:
                from app.config import get_settings
                settings = get_settings()
            start = max(0, float(clip.source_in) - .5)
            end = min(start + MAX_SECONDS, float(asset.get("duration_seconds") or clip.source_out))
            measurements[asset_id] = measure_source(asset, start, end, settings, min(3, remaining))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            profiles.append(VoiceCleanupProfile(asset_id=asset_id, status="unavailable", note="Audio inspection unavailable; source preserved."))
    levels = [m["speech_dbfs"] for m in measurements.values() if m.get("speech_dbfs", -90) >= -55]
    reference = statistics.median(levels) if len(levels) >= 2 else None
    profiles += [choose_profile(key, value, reference) for key, value in measurements.items()]
    if tools.voice_denoise:
        profiles = [p.model_copy(update={"note": p.note.replace(
            "Gentle steady-noise reduction and low rumble filter.",
            "Existing manual denoise retained; automatic denoise not stacked.")[:300]}) for p in profiles]
    tools = tools.model_copy(update={"voice_cleanup_profiles": profiles}, deep=True)
    return plan.model_copy(update={"schema_version": "1.5", "finishing": tools}, deep=True)


def cleanup_manifest(plan):
    tools = plan.finishing
    return {"version": VERSION, "mode": tools.voice_cleanup if tools else "off", "hosted_model_calls": 0,
        "profiles": [p.model_dump(mode="json") for p in tools.voice_cleanup_profiles] if tools and tools.voice_cleanup == "auto" else []}
