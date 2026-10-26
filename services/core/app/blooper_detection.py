"""Conservative transcript clues for possible outtakes, never verified mistakes."""
import math
import re
from collections import defaultdict

from app.take_quality import production_chatter_reason


_CLUES = (
    (r"\b(?:oops|whoops)\b|\b(?:sorry|wait)[,.!]? (?:let's |let us )?(?:start|try) (?:that |it )?again\b", "self_correction"),
    (r"\b(?:i|we) (?:messed|screwed|stuffed) (?:that|this|it) up\b|\b(?:i|we) (?:got|said) that wrong\b", "self_correction"),
    (r"\b(?:can't|cannot|couldn't|can not) (?:even )?(?:say|pronounce|remember)\b|\b(?:hard|difficult) to (?:say|pronounce)\b", "word_stumble"),
    (r"\b(?:forgot|forget) (?:my|the|our) (?:line|lines|words)\b|\b(?:lost|lose) my (?:place|train of thought)\b", "lost_line"),
    (r"\[(?:laughter|laughing|laughs|chuckles)\]|\((?:laughter|laughing|laughs|chuckles)\)|\b(?:ha[ -]){2,}ha\b|\bhahaha\b", "transcribed_laughter"),
)


def find_blooper_evidence(segments: list[dict]) -> dict[int, dict]:
    """Return cited segment IDs and nearby setup/recovery from the same recording.

    No new ASR or hosted model call. A repeated take is a weak clue, not proof
    of a mistake; ordinary sales claims and silence are not classified as errors.
    """
    groups = defaultdict(list)
    for segment in segments:
        start, end = float(segment["start_seconds"]), float(segment["end_seconds"])
        text = " ".join(str(segment.get("text") or "").split())
        if math.isfinite(start + end) and 0 <= start < end and end - start <= 25 and 0 < len(text) <= 900:
            groups[str(segment["asset_id"])].append({**segment, "text": text})
    evidence = {}
    for items in groups.values():
        items.sort(key=lambda item: (float(item["start_seconds"]), int(item["id"])))
        signals = defaultdict(set)
        prefixes = {}
        for index, item in enumerate(items):
            text = item["text"].lower().replace("’", "'")
            signals[index].update(reason for pattern, reason in _CLUES if re.search(pattern, text))
            if production_chatter_reason(text) in {"retake_direction", "editing_discussion"}:
                signals[index].add("retake_direction")
            words = re.findall(r"[a-z0-9']+", text)
            if any(words[n] == words[n + 1] == words[n + 2] for n in range(len(words) - 2)):
                signals[index].add("repeated_start")
            if len(words) >= 5:
                prefix = tuple(words[:5])
                prior = prefixes.get(prefix)
                if prior is not None and 0 <= float(item["start_seconds"]) - float(items[prior]["end_seconds"]) <= 90:
                    signals[prior].add("possible_alternate_take")
                    signals[index].add("possible_alternate_take")
                prefixes[prefix] = index
        flagged = {index: reasons for index, reasons in signals.items() if reasons}
        for index, reasons in flagged.items():
            for neighbour in (index, index - 1, index + 1):
                if not 0 <= neighbour < len(items):
                    continue
                item = items[neighbour]
                gap = max(float(item["start_seconds"]), float(items[index]["start_seconds"])) - min(float(item["end_seconds"]), float(items[index]["end_seconds"]))
                if neighbour != index and gap > 2:
                    continue
                clue = flagged.get(neighbour)
                evidence[int(item["id"])] = {
                    "blooper_candidate": bool(clue),
                    "blooper_signals": sorted(clue or {"nearby_setup_or_recovery"}),
                    "confidence": "possible",
                }
    return evidence
