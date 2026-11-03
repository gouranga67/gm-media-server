"""Small source-context links and a read-only outline of the actual cut.

These are timing/text hints, not semantic or humour scores. They never alter a
plan, invent speech, or trigger a hosted critique request.
"""
import json
import math
import re

_REFERENCE = re.compile(r"^(because|which|it|this|that|they|these|those|their)\b", re.I)
_END = re.compile(r"[.!?][\"'’”]?$|[\])]$")


def _timed(rows):
    """Ignore unusable legacy timestamps instead of breaking optional review."""
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            left, right = float(row["start"]), float(row["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(left + right) and 0 <= left < right:
            result.append({**row, "start": left, "end": right})
    return sorted(result, key=lambda row: row["start"])


def narrative_links(assets, limit=12):
    queues = []
    for asset in assets:
        segments = _timed(asset.get("transcript_segments", []))
        hints = []
        for before, after in zip(segments, segments[1:]):
            gap = float(after.get("start", 0)) - float(before.get("end", 0))
            if not 0 <= gap <= 0.65:
                continue
            reason = "possible_unfinished_sentence" if not _END.search(str(before.get("text", "")).strip()) else (
                "opening_reference" if _REFERENCE.search(str(after.get("text", "")).strip()) else None)
            if reason:
                hints.append({"asset_id": str(asset["asset_id"]),
                    "before": [before["start"], before["end"]], "after": [after["start"], after["end"]],
                    "reason": reason})
        queues.append(hints[:4])
    # Balanced across recordings, rather than spending the whole allowance on
    # the first long take. The full source dialogue is never replaced.
    result = []
    while any(queues) and len(result) < limit:
        for queue in queues:
            if queue and len(result) < limit:
                result.append(queue.pop(0))
    return result


def add_narrative_links(public, max_characters):
    hints = narrative_links(public.get("assets", []))
    if not hints:
        return
    used = len(json.dumps(public, ensure_ascii=False, separators=(",", ":")))
    while hints:
        extra = {"narrative_links": hints}
        size = len(json.dumps(extra, ensure_ascii=False, separators=(",", ":")))
        if size <= 1800 and used + size <= max_characters:
            public.update(extra)
            return
        hints.pop()


def _qualifying_context(words, first, previous_entry, identity):
    preceding = [w for w in words if w["end"] <= first["start"] and first["start"] - w["end"] <= 1.2]
    if not preceding or _END.search(str(preceding[-1].get("text", "")).strip()):
        return None
    boundary = max((index for index, word in enumerate(preceding) if _END.search(str(word.get("text", "")).strip())), default=-1)
    preceding = preceding[boundary + 1:]
    # A previous retained selection may already supply this context. Do not
    # flag a sentence split by an explicit quiet cut as an omitted qualifier.
    if previous_entry and previous_entry["asset_id"] == identity and previous_entry["source_in"] <= preceding[-1]["start"] < previous_entry["source_out"]:
        return None
    text = " ".join(str(w.get("text", w.get("word", ""))).strip() for w in preceding[-6:])
    if re.search(r"\b(?:not|never|without|unless|only|if|isn't|doesn't|don't|cannot|can't)\b", text, re.I):
        return text[:120]
    return None


def story_sequence_review(plan, assets, *, bloopers=False):
    inventory = {str(a["asset_id"]): a for a in assets}
    entries, findings, timeline, seen = [], [], 0.0, set()
    selected_speech = set()
    source_key = lambda asset: str(asset.get("sha256") or asset.get("asset_id"))
    available_speech = {source_key(a) for a in assets if a.get("has_audio") and any(str(s.get("text", "")).strip() or s.get("words") for s in _timed(a.get("transcript_segments", [])))}
    for index, clip in enumerate(plan.clips):
        identity = str(clip.asset_id)
        asset = inventory.get(identity, {})
        left, right = float(clip.source_in), float(clip.source_out)
        duration = float(getattr(clip, "duration", right - left))
        audible = plan.recipe != "montage" or bool(clip.include_source_audio)
        segments = _timed(asset.get("transcript_segments", []))
        all_words = _timed([w for s in segments for w in (s.get("words") or [])])
        words = [w for w in all_words
                 if left <= (w["start"] + w["end"]) / 2 < right] if audible else []
        text = " ".join(str(w.get("text", w.get("word", ""))).strip() for w in words)
        approximate = False
        if audible and not words:
            text = " ".join(str(s.get("text", "")) for s in segments
                if left <= float(s.get("start", 0)) and float(s.get("end", 0)) <= right)
            approximate = bool(text)
        if text and audible:
            selected_speech.add(source_key(asset))
        entry = {"clip_index": index, "asset_id": identity, "start_seconds": round(timeline, 3),
                 "end_seconds": round(timeline + duration, 3), "source_in": left, "source_out": right,
                 "role": clip.story_role, "text": text[:360], "word_timed": bool(words),
                 "partial_transcript": approximate}
        qualifier = _qualifying_context(all_words, words[0], entries[-1] if entries else None, identity) if words else None
        if qualifier:
            entry["preceding_qualifier"] = qualifier
            findings.append(f"Clip {index + 1}: its recorded lead-in contains qualifying language (\"{qualifier}\") outside this selection. Check whether removing it changes the meaning; this is a text hint, not a semantic verdict.")
        if words and (float(words[0]["start"]) < left - 0.03 or float(words[-1]["end"]) > right + 0.03):
            findings.append(f"Clip {index + 1}: the cut may overlap a recorded word boundary; listen at the join.")
        tokens = re.findall(r"[a-z0-9']+", text.lower())
        key = tuple(tokens)
        if len(tokens) >= 8 and key in seen and not bloopers:
            findings.append(f"Clip {index + 1}: this recorded passage repeats an earlier selection; check whether the repetition is intentional.")
        seen.add(key)
        if text and _REFERENCE.search(text) and entries and entries[-1]["asset_id"] != identity:
            findings.append(f"Clip {index + 1}: opens on a reference or connecting word after a source change; check that its setup is understandable.")
        entries.append(entry)
        timeline += duration
    if plan.finishing and plan.finishing.audio_joins:
        findings.append("Audio leads or tails overlap neighbouring picture clips; the outline shows picture source passages. Review the complete spoken joins in playback.")
    pictures = {str(c.asset_id) for c in plan.broll}
    if plan.finishing:
        pictures.update(str(layer.asset_id) for layer in plan.finishing.layers)
    return {"version": 2, "status": "attention" if findings else "checked", "outline": entries,
            "findings": findings[:8], "hosted_model_calls": 0,
            "source_coverage": {"available_speech_recordings": len(available_speech), "selected_speech_recordings": len(selected_speech),
                "supporting_picture_sources": len({source_key(inventory.get(identity, {"asset_id": identity})) for identity in pictures}),
                "unused_speech_recordings": len(available_speech - selected_speech),
                "note": "Counts unique source checksums when available. Selection is not a quota: using every recording does not establish a better story."},
            "semantic_judgement": "human_review_required", "intent": "bloopers" if bloopers else "story"}
