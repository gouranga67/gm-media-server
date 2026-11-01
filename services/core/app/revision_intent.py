"""Conservative local revision commands and server-enforced user protections.

Only whole, unambiguous commands use the local lane. Everything else retains
the existing planner. No fuzzy phrase selection or inferred source timestamps.
"""
import math
import re
from copy import deepcopy


def _tokens(text):
    return re.findall(r"[a-z0-9']+", str(text).lower().replace("’", "'"))


def _spoken(document, assets):
    inventory = {str(a["asset_id"]): a for a in assets}
    result = []
    for clip in document.get("clips", []):
        if document.get("recipe") == "montage" and not clip.get("include_source_audio"):
            continue
        asset = inventory.get(str(clip.get("asset_id")), {})
        left, right = float(clip.get("source_in", 0)), float(clip.get("source_out", 0))
        words, complete = [], True
        for segment in asset.get("transcript_segments", []):
            try:
                start, end = float(segment["start"]), float(segment["end"])
            except (KeyError, TypeError, ValueError):
                complete = False
                continue
            if end <= left or start >= right:
                continue
            timed = []
            for word in segment.get("words") or []:
                try:
                    a, b = float(word["start"]), float(word["end"])
                    if not math.isfinite(a + b) or not 0 <= a < b:
                        raise ValueError("unusable word timing")
                    timed.append({**word, "start": a, "end": b})
                except (KeyError, TypeError, ValueError):
                    complete = False
            if _tokens(" ".join(str(w.get("text", w.get("word", ""))) for w in timed)) != _tokens(segment.get("text", "")):
                complete = False
            words.extend(timed)
        words.sort(key=lambda w: w["start"])
        selected = [w for w in words if left <= (float(w["start"]) + float(w["end"])) / 2 < right]
        if selected and complete:
            result.extend(_tokens(" ".join(str(w.get("text", w.get("word", ""))) for w in selected)))
        else:
            # Missing ASR cannot establish equivalence of different selections.
            result.append((str(clip.get("asset_id")), left, right))
    return result


def assert_revision_locks(document, previous, locks, assets):
    problems = []
    before_tools, after_tools = previous.get("finishing") or {}, document.get("finishing") or {}
    if "spoken phrases" in locks and _spoken(document, assets) != _spoken(previous, assets):
        problems.append("spoken phrases")
    if "spoken phrases" in locks and before_tools.get("audio_joins", []) != after_tools.get("audio_joins", []):
        problems.append("spoken phrases")
    if "clip order" in locks:
        old = previous.get("clips", [])
        positions = []
        for clip in document.get("clips", []):
            identity = str(clip.get("asset_id"))
            matches = [(max(0, min(float(clip.get("source_out", 0)), float(c.get("source_out", 0)))
                            - max(float(clip.get("source_in", 0)), float(c.get("source_in", 0)))), i)
                       for i, c in enumerate(old) if str(c.get("asset_id")) == identity]
            best = max(matches, default=(0, -1))
            # Image clips have zero source ranges: preserve their occurrence.
            if clip.get("media_kind") == "image":
                best = next(((1, i) for i, c in enumerate(old) if str(c.get("asset_id")) == identity
                             and (not positions or i >= positions[-1])), (0, -1))
            positions.append(best[1] if best[0] > 0 else -1)
        if -1 in positions or positions != sorted(positions):
            problems.append("clip order")
    fields = {
        "captions": (("caption_style", None), ("caption_position", "lower_safe"), ("caption_timing_offset_seconds", 0)),
        "music": (("music_track_id", None), ("music_mix", "none")),
        "effects": (("effects", []),),
    }
    for lock, keys in fields.items():
        if lock in locks and any(document.get(k, default) != previous.get(k, default) for k, default in keys):
            problems.append(lock)
    tool_fields = {"captions": ("caption_regions",), "music": ("music_start_seconds", "music_regions"),
                   "effects": ("callouts", "pointers")}
    for lock, keys in tool_fields.items():
        if lock in locks and any(before_tools.get(k, 0 if k == "music_start_seconds" else []) !=
                                 after_tools.get(k, 0 if k == "music_start_seconds" else []) for k in keys):
            problems.append(lock)
    if problems:
        raise ValueError("revision changed protected " + ", ".join(dict.fromkeys(problems)) + "; preserve these elements or explicitly unlock them")


def local_revision(document, instruction, locks=()):
    """Return a minimal patch only for an exact supported command, else None."""
    text = " ".join(str(instruction).strip().lower().split()).rstrip(".! ")
    text = re.sub(r"^please ", "", text)
    candidate = deepcopy(document)
    domain = None
    match = re.fullmatch(r"(?:move|put|set) (?:the )?(?:captions|subtitles)(?: position)? (?:to|at|in) (?:the )?(top|upper|middle|center|bottom|lower)(?: of (?:the )?(?:screen|frame))?", text)
    if match:
        domain = "captions"
        candidate["caption_position"] = {"top": "upper", "upper": "upper", "middle": "middle", "center": "middle", "bottom": "lower_safe", "lower": "lower_safe"}[match[1]]
        # Explicit visible regions otherwise override the global setting and
        # make a successful command appear to do nothing. Preserve hidden cues.
        for region in (candidate.get("finishing") or {}).get("caption_regions", []):
            if region.get("position", "lower_safe") != "hidden":
                region["position"] = candidate["caption_position"]
    elif re.fullmatch(r"(?:remove|disable|turn off) (?:all |the )?(?:b[ -]?roll|cutaways)", text):
        domain = "broll"
        candidate["broll"] = []
    elif re.fullmatch(r"(?:remove|disable|turn off) (?:all |the )?(?:creative |sound and visual )?(?:effects|fx)", text):
        domain = "effects"
        candidate["effects"] = []
        tools = candidate.get("finishing") or {}
        for key in ("callouts", "pointers"):
            tools.pop(key, None)
    else:
        match = re.fullmatch(r"(?:make )?clip ([1-9][0-9]?) (louder|quieter) by ([0-9]+(?:\.[0-9]+)?)\s*db", text)
        if not match:
            return None
        domain = "audio"
        index, delta = int(match[1]) - 1, float(match[3]) * (1 if match[2] == "louder" else -1)
        if not 0 <= index < len(candidate.get("clips", [])):
            raise ValueError("That clip is not in the saved edit; refresh and use a current clip number")
        clip = candidate["clips"][index]
        if candidate.get("recipe") == "montage" and not clip.get("include_source_audio"):
            return None
        gain = float(clip.get("source_audio_gain_db") or 0) + delta
        if not -12 <= gain <= 12 or delta == 0:
            raise ValueError("Clip volume must stay between -12 and +12 dB and the requested change must be nonzero")
        clip["source_audio_gain_db"] = gain
    if domain in locks:
        raise ValueError(f"{domain.capitalize()} are protected; unlock {domain} before requesting this change")
    return candidate, {"route": "local", "scope": domain, "additional_model_calls": 0}
