"""Exact single-request revisions grounded in the saved audible source words.

No fuzzy quote matching, invented timings, new editor calls or automatic retries.
The API freezes a resolution before queueing; the worker replays that document.
"""

import math
import re
from copy import deepcopy

from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan, apply_timeline_adjustments, document_sha256
from app.finishing_tools import FinishingTools

VERSION = 1
_QUOTE = r'''(?:"(?P<plain>[^"\n]{1,160})"|“(?P<curly>[^”\n]{1,160})”|'(?P<single>[^\n]{1,160}?)')'''
_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
_LOCATION = r"(?: in clip (?P<clip>[1-9][0-9]?))?"
_AUDIO = re.compile(r"(?:make|turn up|turn down|boost) (?:the (?:phrase|words|line) )?" + _QUOTE
    + r"(?: (?P<direction>louder|quieter))?(?: by (?P<amount>" + _NUMBER + r")\s*db)?" + _LOCATION, re.I)
_PAUSE = re.compile(r"(?:shorten|reduce|trim) (?:the )?pause after " + _QUOTE
    + r"(?: to (?P<seconds>" + _NUMBER + r")\s*(?:seconds?|s))?" + _LOCATION, re.I)


def revision_spec(instruction):
    text = re.sub(r"^please\s+", "", str(instruction).strip(), flags=re.I).rstrip(".! ")
    for pattern, kind in ((_AUDIO, "phrase_audio"), (_PAUSE, "phrase_pause")):
        match = pattern.fullmatch(text)
        if not match:
            continue
        value = match.groupdict()
        value["direction"] = str(value.get("direction") or "").lower()
        phrase = value.get("plain") or value.get("curly") or value.get("single")
        if kind == "phrase_audio" and not value.get("direction") and text.lower().startswith("make "):
            return None
        if kind == "phrase_audio" and ((text.lower().startswith("turn down ") and value.get("direction") == "louder")
                or (text.lower().startswith(("turn up ", "boost ")) and value.get("direction") == "quieter")):
            return None
        return {"kind": kind, "phrase": phrase, "clip_index": int(value["clip"]) - 1 if value.get("clip") else None,
            "delta_db": float(value.get("amount") or 3) * (-1 if value.get("direction", "") == "quieter" or text.lower().startswith("turn down ") else 1)
                if kind == "phrase_audio" else None,
            "pause_seconds": float(value.get("seconds") or .5) if kind == "phrase_pause" else None}
    return None


def tokens(text):
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", str(text).casefold().replace("’", "'"))


def _words(asset, left, right):
    result, seen = [], set()
    for segment in asset.get("transcript_segments") or []:
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            if not isinstance(word, dict):
                continue
            try:
                a, b = float(word["start"]), float(word["end"])
            except (TypeError, ValueError, KeyError):
                continue
            text = str(word.get("text", word.get("word", ""))).strip()
            identity = (a, b, text)
            if math.isfinite(a + b) and left - .001 <= a < b <= right + .001 and identity not in seen:
                result.append({**word, "start": a, "end": b, "text": text})
                seen.add(identity)
    return sorted(result, key=lambda w: (w["start"], w["end"]))


def phrase_candidates(document, assets, spec):
    """Only actual audible occurrences count, including valid J/L extensions."""
    wanted = tokens(spec["phrase"])
    if not wanted:
        raise ValueError("Quote at least one recorded word.")
    inventory = {str(a["asset_id"]): a for a in assets}
    joins = {int(j["clip_index"]): j for j in (document.get("finishing") or {}).get("audio_joins", [])}
    timeline, spans = 0.0, []
    for index, clip in enumerate(document["clips"]):
        duration = float(clip.get("duration", float(clip["source_out"]) - float(clip["source_in"])))
        join = joins.get(index, {})
        lead, tail = float(join.get("lead_seconds", 0)), float(join.get("tail_seconds", 0))
        spans.append((timeline - lead, timeline + duration + tail, lead, tail))
        timeline += duration
    candidates = []
    for index, clip in enumerate(document["clips"]):
        if spec.get("clip_index") is not None and spec["clip_index"] != index:
            continue
        if document["recipe"] == "montage" and not clip.get("include_source_audio"):
            continue
        asset_id = str(clip["asset_id"])
        start, _, lead, tail = spans[index]
        left, right = float(clip["source_in"]) - lead, float(clip["source_out"]) + tail
        words = _words(inventory.get(asset_id, {}), left, right)
        flattened = [(token, wi) for wi, word in enumerate(words) for token in tokens(word["text"])]
        for at in range(len(flattened) - len(wanted) + 1):
            sequence = flattened[at:at + len(wanted)]
            if [token for token, _ in sequence] != wanted:
                continue
            first, last = sequence[0][1], sequence[-1][1]
            # Do not match only part of a hyphenated/numeric ASR word.
            if (at and flattened[at - 1][1] == first) or (at + len(wanted) < len(flattened) and flattened[at + len(wanted)][1] == last):
                continue
            a, b = words[first]["start"], words[last]["end"]
            if b - a > 20:
                continue
            reel_a, reel_b = start + a - left, start + b - left
            if any(j != index and min(reel_b, spans[j][1]) > max(reel_a, spans[j][0]) + .001 for j in joins):
                continue  # This picture clip's source voice is muted by another J/L take.
            candidates.append({"clip_index": index, "asset_id": asset_id, "source_in": a, "source_out": b,
                "start_seconds": round(reel_a, 3), "end_seconds": round(reel_b, 3),
                "words": words, "last_word_index": last, "phrase": " ".join(w["text"] for w in words[first:last + 1])})
    return candidates


def add_voice_region(document, start, end, delta):
    """Add to existing automation only inside this interval; retain outside gains."""
    current = (document.get("finishing") or {}).get("audio_regions", [])
    boundaries = sorted({start, end, *(float(r[k]) for r in current for k in ("start", "end"))})
    regions = []
    for left, right in zip(boundaries, boundaries[1:]):
        if right - left < .0001:
            continue
        center = (left + right) / 2
        existing = next((float(r["gain_db"]) for r in current if r["start"] <= center < r["end"]), 0)
        gain = existing + (delta if start <= center < end else 0)
        if not -12 <= gain <= 12:
            raise ValueError("The phrase's combined volume must stay between -12 and +12 dB. Use the phrase audio controls to review its existing gain.")
        if not gain:
            continue
        if regions and regions[-1]["gain_db"] == gain and abs(regions[-1]["end"] - left) < .0001:
            regions[-1]["end"] = right
        else:
            regions.append({"start": left, "end": right, "gain_db": gain})
    tools = FinishingTools.model_validate({**(document.get("finishing") or {}), "audio_regions": regions})
    return {**document, "schema_version": "1.5", "finishing": tools.model_dump(mode="json")}


def measured_quiet(asset, start, end, settings=None):
    """At most one 20-second source interval, three-second decode budget."""
    from app.config import get_settings
    from app.media_analysis import resolve_source, run_command
    from app.quality_review import parse_render_measurements
    settings = settings or get_settings()
    source = resolve_source(settings.media_root, asset["_storage_key"])
    result = run_command(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-ss", f"{start:.3f}",
        "-t", f"{end-start:.3f}", "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn", "-af",
        "silencedetect=noise=-42dB:d=0.12", "-f", "null", "-"], timeout=3)
    return [[start + item["start"], start + item["end"]] for item in parse_render_measurements(result.stderr, end - start)["silence_intervals"]]


def resolve_revision(document, instruction, assets, locks=(), *, quiet_probe=None):
    spec = revision_spec(instruction)
    if spec is None:
        return None
    if spec["kind"] == "phrase_audio" and (not 0 < abs(spec["delta_db"]) <= 12):
        raise ValueError("Use a nonzero phrase volume change of at most 12 dB.")
    if spec["kind"] == "phrase_pause" and not .3 <= spec["pause_seconds"] <= 2:
        raise ValueError("Choose a retained pause between 0.3 and 2 seconds to protect word endings.")
    matches = phrase_candidates(document, assets, spec)
    if not matches:
        raise ValueError("That quote was not found as complete, word-timed speech in this saved edit. Copy the recorded wording or use the precise clip controls; corrected subtitle text may differ.")
    if len(matches) > 1:
        choices = ", ".join(f"clip {m['clip_index'] + 1} at {m['start_seconds']:.1f}s" for m in matches[:5])
        if len({m["clip_index"] for m in matches}) == 1:
            raise ValueError(f"That quote repeats within the same clip ({choices}). Quote a longer unique phrase or use the precise clip controls; no new edit was queued.")
        raise ValueError(f"That quote occurs more than once ({choices}). Add 'in clip N' to choose one; no new edit was queued.")
    target = matches[0]
    original = deepcopy(document)
    candidate = deepcopy(document)
    mapping = None
    detail = {key: target[key] for key in ("clip_index", "asset_id", "source_in", "source_out", "start_seconds", "end_seconds", "phrase")}
    if spec["kind"] == "phrase_audio":
        candidate = add_voice_region(candidate, target["start_seconds"], target["end_seconds"], spec["delta_db"])
        detail["delta_db"] = spec["delta_db"]
        summary = f"Changed only the matched phrase's voice automation by {spec['delta_db']:+g} dB."
    else:
        if (candidate.get("finishing") or {}).get("audio_joins"):
            raise ValueError("This edit has independent audio joins. Clear those joins before shortening a pause, or use a separate audio-level change.")
        words, last = target["words"], target["last_word_index"]
        if last + 1 >= len(words):
            raise ValueError("No following word-timed speech exists in this clip. Select the trailing pause in the precise clip controls.")
        left, right = words[last]["end"], words[last + 1]["start"]
        if right - left > 20 or right - left <= spec["pause_seconds"] + .1:
            raise ValueError("The following gap is already short, or exceeds the bounded pause inspection. Use the precise clip controls.")
        from app.speech_precision import boundary_margins
        asset = next(a for a in assets if str(a["asset_id"]) == target["asset_id"])
        active = bool(asset.get("speech_precision"))
        safe_left = left + boundary_margins(words[last], active)[1]
        safe_right = right - boundary_margins(words[last + 1], active)[0]
        try:
            quiet = (quiet_probe or measured_quiet)(asset, left, right)
        except Exception as error:
            raise ValueError("Could not verify quiet audio in the selected pause. The edit was preserved; use the precise clip controls.") from error
        intervals = [(max(safe_left, float(a)), min(safe_right, float(b))) for a, b in quiet
            if math.isfinite(float(a) + float(b)) and min(safe_right, float(b)) > max(safe_left, float(a))]
        a, b = max(intervals, key=lambda p: p[1] - p[0], default=(0, 0))
        # Preserve all non-quiet reaction audio and conservative word handles.
        retained_quiet = max(.08, spec["pause_seconds"] - ((right - left) - (b - a)))
        if b - a <= retained_quiet + .08:
            raise ValueError("No safely removable quiet interval was verified after that quote. Reactions/noise were preserved; use the precise clip controls if you want to remove them.")
        model = MontageEditPlan if candidate["recipe"] == "montage" else TalkingHeadEditPlan
        plan = model.model_validate(candidate)
        revised = apply_timeline_adjustments(plan, [{"clip_index": target["clip_index"], "max_pause_seconds": retained_quiet,
            "verified_pause_ranges": [[a, b]]}], assets)
        duration = lambda p: sum(float(c.get("duration", c["source_out"] - c["source_in"])) for c in p["clips"])
        candidate = revised.model_dump(mode="json")
        removed = duration(original) - duration(candidate)
        if removed < .05:
            raise ValueError("That pause cannot be shortened safely within the clip bounds; the edit was preserved.")
        index = target["clip_index"]
        pieces = revised.clips[index:index + len(revised.clips) - len(plan.clips) + 1]
        if len(pieces) != 2:
            raise ValueError("The pause change did not produce one verified cut; use the precise clip controls.")
        clip_at = target["start_seconds"] - (target["source_in"] - float(plan.clips[index].source_in))
        cut_left = clip_at + float(pieces[0].source_out) - float(plan.clips[index].source_in)
        cut_right = clip_at + float(pieces[1].source_in) - float(plan.clips[index].source_in)
        mapping = [[0, cut_left, 0], [cut_right, duration(original), cut_left]]
        detail.update(quiet_source_range=[round(a, 3), round(b, 3)], removed_seconds=round(removed, 3),
            retained_pause_seconds=round(right - left - removed, 3), requested_pause_seconds=spec["pause_seconds"])
        summary = f"Removed {removed:.2f}s of measured quiet audio after the quote; kept word handles and non-quiet reactions."
    from app.revision_intent import assert_revision_locks
    assert_revision_locks(candidate, original, locks, assets)
    return {"version": VERSION, "base_plan_sha256": document_sha256(original), "document": candidate, "timeline_mapping": mapping,
        "document_sha256": document_sha256(candidate), "execution": {"route": "local", "scope": spec["kind"],
            "additional_model_calls": 0, "summary": summary, "target": detail}}


def replay_resolution(resolution, previous):
    if resolution.get("version") != VERSION or resolution.get("base_plan_sha256") != document_sha256(previous):
        raise ValueError("The grounded revision no longer matches its saved base plan; refresh and submit again.")
    document = deepcopy(resolution["document"])
    if document_sha256(document) != resolution.get("document_sha256"):
        raise ValueError("The saved revision resolution failed its integrity check.")
    return document, deepcopy(resolution["execution"])
