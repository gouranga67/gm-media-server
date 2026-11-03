"""Versioned alignment caches and conservative speech-boundary policy."""

import hashlib
import fcntl
import json
import math
import re
import time
from copy import deepcopy
from psycopg.types.json import Jsonb

from app.media_analysis import atomic_write, resolve_source
from app.speech_alignment import MODEL_REVISION


VERSION = "speech_precision_v1"
MAX_WINDOW_SECONDS = 12
MAX_WORDS = 50


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def profile(settings):
    return f"{VERSION}:{getattr(settings, 'speech_alignment_model_revision', MODEL_REVISION)}"


def normal_word(text):
    value = str(text).strip().replace("’", "'").strip(".,!?;:\"“”()[]{}…").replace("-", " ").upper()
    return value if value and re.fullmatch(r"[A-Z]+(?:[' -][A-Z]+)*", value) else None


def valid_word(word):
    try:
        start, end = float(word["start"]), float(word["end"])
        return math.isfinite(start + end) and 0 <= start < end
    except (ValueError, TypeError, KeyError):
        return False


def windows(segments):
    for si, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        group = []
        for wi, word in enumerate(segment.get("words") or []):
            supported = isinstance(word, dict) and valid_word(word) and normal_word(word.get("text", ""))
            if group and (not supported or len(group) >= MAX_WORDS or
                          float(word["end"]) - float(group[0][1]["start"]) > MAX_WINDOW_SECONDS - 1.6):
                yield si, group
                group = []
            if supported and float(word["end"]) - float(word["start"]) < MAX_WINDOW_SECONDS - 1.6:
                group.append((wi, word))
        if group:
            yield si, group


def accept_alignment(words, candidates, *, left=0, right=math.inf):
    """An uncertain forced match must not overwrite better source estimates."""
    if not isinstance(candidates, list) or len(words) != len(candidates):
        return None
    try:
        group_score = sum(float(c.get("score", 0)) for c in candidates) / len(candidates)
    except (TypeError, ValueError, AttributeError, ZeroDivisionError):
        return None
    output = []
    for word, item in zip(words, candidates):
        try:
            start, end, score = float(item["start"]), float(item["end"]), float(item["score"])
        except (ValueError, TypeError, KeyError):
            output.append(dict(word))
            continue
        if (not math.isfinite(start + end + score) or not (0.2 if group_score >= 0.45 else 0.6) <= score <= 1 or
                not left <= start < end <= right or end - start < 0.035 or
                end - start > 3 or abs(start - word["start"]) > 0.9 or abs(end - word["end"]) > 0.9):
            output.append(dict(word))
        else:
            output.append({**word, "start": round(start, 3), "end": round(end, 3),
                           "timing_source": "ctc_aligned" if score >= 0.6 else "ctc_uncertain", "alignment_score": round(score, 4)})
    if not any(w.get("timing_source") == "ctc_aligned" for w in output):
        return None
    # Whisper's entire sentence can be early. Keeping one rejected name at its
    # old time would overlap every corrected neighbouring word. Estimate that
    # short unsupported run BETWEEN reliable anchors, label it explicitly, and
    # give it conservative cut margins. Never claim interpolation is alignment.
    index = 0
    while index < len(output):
        if output[index].get("timing_source", "").startswith("ctc_"):
            index += 1
            continue
        first = index
        while index < len(output) and not output[index].get("timing_source", "").startswith("ctc_"):
            index += 1
        last = index - 1
        span = words[last]["end"] - words[first]["start"]
        begin = output[first - 1]["end"] if first else max(left, output[index]["start"] - span - .08)
        finish = output[index]["start"] if index < len(output) else min(right, begin + span + .08)
        if not 0.03 <= finish - begin <= span + .8 or finish - begin < span / 3:
            return None
        for wi in range(first, last + 1):
            start = begin + (words[wi]["start"] - words[first]["start"]) / span * (finish - begin)
            end = begin + (words[wi]["end"] - words[first]["start"]) / span * (finish - begin)
            if max(abs(start - words[wi]["start"]), abs(end - words[wi]["end"])) > .9:
                return None
            output[wi] = {**words[wi], "start": round(start, 3), "end": round(end, 3),
                          "timing_source": "interpolated", "alignment_score": 0.0}
    if any(a["end"] > b["start"] for a, b in zip(output, output[1:])):
        return None
    return output


def _cache_path(settings, key):
    return resolve_source(settings.media_root, key)


def read_snapshot(settings, key):
    if not isinstance(key, str) or not re.fullmatch(
            r"analysis/speech-precision/[a-f0-9]{64}/[a-f0-9]{16}/[a-f0-9]{64}/snapshots/[a-f0-9]{64}\.json", key):
        raise ValueError("invalid speech timing snapshot")
    value = json.loads(_cache_path(settings, key).read_text())
    if (not isinstance(value, dict) or value.get("version") != VERSION or not isinstance(value.get("segments"), list)
            or digest(value) != key.rsplit("/", 1)[-1][:-5]):
        raise ValueError("invalid speech timing snapshot")
    return value


def align_source(source, transcript, source_sha, settings, *, budget=None, resume=False, backend_factory=None):
    # Duplicate imports and foreground/background callers share the same cache.
    # Lock snapshot publication too: atomic_write uses a predictable temp name.
    if not re.fullmatch(r"[a-f0-9]{64}", str(source_sha)):
        raise ValueError("speech alignment requires a verified source fingerprint")
    directory = settings.media_root / "analysis" / "speech-precision" / source_sha
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "cache.lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            return _align_source(source, transcript, source_sha, settings, budget=budget,
                                 resume=resume, backend_factory=backend_factory)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _align_source(source, transcript, source_sha, settings, *, budget=None, resume=False, backend_factory=None):
    """Cache each bounded window, then publish an immutable timing snapshot.

    The small mutable index points to the newest result; saved edits reference
    the immutable result itself, so later analysis cannot alter an approval.
    """
    if not re.fullmatch(r"[a-f0-9]{64}", str(source_sha)):
        raise ValueError("speech alignment requires a verified source fingerprint")
    original_digest = digest(transcript)
    prefix = f"analysis/speech-precision/{source_sha}/{digest(profile(settings))[:16]}/{original_digest}"
    root = settings.media_root / prefix
    index = root / "current.json"
    try:
        key = json.loads(index.read_text())["snapshot_key"]
        cached = read_snapshot(settings, key)
        if (key.startswith(prefix + "/snapshots/") and cached.get("transcript_sha256") == original_digest
                and cached.get("source_sha256") == source_sha and cached.get("profile") == profile(settings)
                and (cached.get("complete") or not resume)):
            return key, cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    started = time.monotonic()
    limit = budget if budget is not None else settings.speech_alignment_budget_seconds
    segments = deepcopy(transcript.get("segments") or [])
    total = sum(len(s.get("words") or []) for s in segments if isinstance(s, dict))
    report = {"version": VERSION, "profile": profile(settings), "transcript_sha256": original_digest,
              "source_sha256": source_sha, "segments": segments, "total_words": total,
              "aligned_words": 0, "uncertain_words": 0, "interpolated_words": 0,
              "complete": True, "hosted_model_calls": 0}
    if transcript.get("language") not in {"en", "english"}:
        report["status"] = "unsupported_language"
    else:
        from app.resource_guard import inference_slot
        from app.speech_alignment import LocalAligner
        engine = None
        entered = False
        try:
            with inference_slot(settings.media_root):
                for si, group in windows(segments):
                    raw_words = [w for _, w in group]
                    key = digest({"segment": si, "words": raw_words})
                    cache = root / "windows" / f"{key}.json"
                    try:
                        result = json.loads(cache.read_text())
                        accepted = result["words"]
                        if accepted is not None and (not isinstance(accepted, list) or len(accepted) != len(group)
                                or any(not isinstance(w, dict) or not valid_word(w) or w.get("text") != raw.get("text")
                                       for w, raw in zip(accepted, raw_words))):
                            raise ValueError("invalid cached word timing")
                    except (OSError, ValueError, KeyError, TypeError):
                        if time.monotonic() - started >= limit:
                            report["complete"] = False
                            break
                        if engine is None:
                            engine = (backend_factory or LocalAligner)(settings)
                            engine.__enter__()
                            entered = True
                        # Preserve neighbouring excluded/unsupported words. Alignment
                        # gets context padding, but accepted words cannot cross them.
                        all_words = segments[si].get("words") or []
                        before = all_words[group[0][0] - 1] if group[0][0] else None
                        after = all_words[group[-1][0] + 1] if group[-1][0] + 1 < len(all_words) else None
                        left = float(before["end"]) if isinstance(before, dict) and valid_word(before) else 0
                        right = float(after["start"]) if isinstance(after, dict) and valid_word(after) else float(transcript.get("duration_seconds") or raw_words[-1]["end"] + 0.4)
                        if before is None and si:
                            previous_words = [w for s in segments[:si] if isinstance(s, dict)
                                              for w in s.get("words") or [] if isinstance(w, dict) and valid_word(w)]
                            if previous_words:
                                left = previous_words[-1]["end"]
                        if after is None and si + 1 < len(segments):
                            following_words = [w for s in segments[si + 1:] if isinstance(s, dict)
                                               for w in s.get("words") or [] if isinstance(w, dict) and valid_word(w)]
                            if following_words:
                                right = following_words[0]["start"]
                        start = max(left, 0, raw_words[0]["start"] - 0.75)
                        end = min(right, raw_words[-1]["end"] + 0.75)
                        candidates = engine.align(source, start, end, [normal_word(w["text"]) for w in raw_words]) if end - start >= .1 else None
                        accepted = accept_alignment(raw_words, candidates, left=left, right=right)
                        result = {"words": accepted}
                        atomic_write(cache, json.dumps(result))
                    accepted = result.get("words")
                    if isinstance(accepted, list) and len(accepted) == len(group):
                        for (wi, _), word in zip(group, accepted):
                            segments[si]["words"][wi] = word
                        report["aligned_words"] += sum(w.get("timing_source") == "ctc_aligned" for w in accepted)
                        report["uncertain_words"] += sum(w.get("timing_source") == "ctc_uncertain" for w in accepted)
                        report["interpolated_words"] += sum(w.get("timing_source") == "interpolated" for w in accepted)
                report["status"] = "aligned" if report["aligned_words"] == total and total else "partial" if report["aligned_words"] else "estimated"
        except Exception as error:
            report["status"] = "unavailable"
            report["reason"] = type(error).__name__
            # No repeated background hot loop when dependencies/model are absent.
            report["complete"] = True
        finally:
            if entered:
                engine.__exit__(None, None, None)
    # Segment bounds must contain refined words, or caption construction clips
    # the very first/last syllable back to the recognizer's older segment bound.
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        words = [w for w in segment.get("words") or [] if isinstance(w, dict) and valid_word(w)]
        if words:
            segment["start"] = min(float(segment.get("start", words[0]["start"])), min(w["start"] for w in words))
            segment["end"] = max(float(segment.get("end", words[-1]["end"])), max(w["end"] for w in words))
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    snapshot_key = f"{prefix}/snapshots/{digest(report)}.json"
    atomic_write(settings.media_root / snapshot_key, json.dumps(report, ensure_ascii=False))
    atomic_write(index, json.dumps({"snapshot_key": snapshot_key}))
    return snapshot_key, report


def summary(payload):
    return {k: payload.get(k) for k in ("version", "status", "total_words", "aligned_words", "uncertain_words", "interpolated_words", "complete")}


def apply_snapshot(context, snapshot, settings):
    """Only a saved snapshot opts a run into the new boundary policy."""
    if not isinstance(snapshot, dict) or snapshot.get("version") != VERSION:
        return
    keys = snapshot.get("assets") or {}
    for asset in context["assets"]:
        asset["speech_precision"] = {"version": VERSION, "status": "estimated"}
        key = keys.get(str(asset["asset_id"]))
        if key:
            payload = read_snapshot(settings, key)
            if payload.get("source_sha256") != asset.get("sha256"):
                raise ValueError("speech timing snapshot does not match its source")
            asset["transcript_segments"] = deepcopy(payload["segments"])
            asset["speech_precision"] = summary(payload)
    context["speech_precision"] = {
        "version": VERSION, "hosted_model_calls": 0,
        "aligned_words": sum(int(a.get("speech_precision", {}).get("aligned_words") or 0) for a in context["assets"]),
        "source_count": len(keys),
        "note": "Aligned words retain the original transcript text; uncertain timing keeps conservative margins.",
    }


def prepare_context(context, settings):
    snapshot = {"version": VERSION, "assets": {}}
    deadline = time.monotonic() + settings.speech_alignment_edit_budget_seconds
    if not settings.speech_alignment_enabled:
        return {}
    for asset in context["assets"]:
        if not asset.get("_storage_key") or not asset.get("_transcript_key") or not asset.get("sha256"):
            continue
        original = json.loads(resolve_source(settings.media_root, asset["_transcript_key"]).read_text())
        if not original.get("segments"):
            continue
        remaining = max(0, deadline - time.monotonic())
        key, _ = align_source(resolve_source(settings.media_root, asset["_storage_key"]),
            original, asset["sha256"], settings, budget=remaining)
        snapshot["assets"][str(asset["asset_id"])] = key
    apply_snapshot(context, snapshot, settings)
    return snapshot


def boundary_margins(word, active=False):
    if not active:
        return 0.12, 0.16
    try:
        score = float(word.get("alignment_score") or 0)
        probability = float(word.get("probability", 1) or 0)
    except (TypeError, ValueError):
        score, probability = 0, 0
    if word.get("timing_source") == "ctc_aligned" and math.isfinite(score) and score >= 0.6:
        return 0.10, 0.16
    if word.get("timing_source") in {"ctc_uncertain", "interpolated"} or not math.isfinite(probability) or probability < 0.5:
        return 0.22, 0.28
    return 0.16, 0.22


def backfill_one(settings, connect):
    """One existing source per idle worker turn; no jobs or AI requests."""
    if not getattr(settings, "speech_alignment_enabled", False):
        return False
    with connect() as database:
        row = database.execute(
            """SELECT a.id, a.sha256, a.storage_key, i.manifest
               FROM assets a JOIN asset_ingests i ON i.asset_id=a.id
               WHERE a.status='ready' AND i.status='ready' AND a.library_status='active'
                 AND i.manifest #>> '{derived,transcript}' IS NOT NULL
                 AND i.manifest #>> '{derived,speech_precision_profile}' IS DISTINCT FROM %s
               ORDER BY i.completed_at, a.id LIMIT 1""", (profile(settings),)
        ).fetchone()
    if row is None:
        return False
    manifest = row["manifest"]
    transcript = json.loads(resolve_source(settings.media_root, manifest["derived"]["transcript"]).read_text())
    key, payload = align_source(resolve_source(settings.media_root, row["storage_key"]),
        transcript, row["sha256"], settings, resume=True)
    updated = deepcopy(manifest)
    updated["derived"]["speech_precision"] = key
    updated["derived"]["speech_precision_summary"] = summary(payload)
    if payload.get("complete"):
        updated["derived"]["speech_precision_profile"] = profile(settings)
    with connect() as database:
        result = database.execute(
            """UPDATE asset_ingests SET manifest=%s, updated_at=now()
               WHERE asset_id=%s AND status='ready' AND manifest=%s""",
            (Jsonb(updated), row["id"], Jsonb(manifest)),
        )
        if result.rowcount and updated.get("manifest_path"):
            atomic_write(resolve_source(settings.media_root, updated["manifest_path"]), json.dumps(updated, ensure_ascii=False))
    return True
