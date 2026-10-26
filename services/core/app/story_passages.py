"""Source-backed sentence windows for ordinary concept discovery; no new ASR."""

import hashlib
import re
from copy import deepcopy

from app.blooper_focus import _words

_END = re.compile(r"[.!?][\"'’”]?$")
_PREFIX = re.compile(r"^(?:(?:all right|alright|okay|ok|um|uh|erm)[,;:]\s*)+", re.I)


def _identity(asset: str, start: float, end: float, text: str) -> int:
    # Negative 52-bit IDs cannot collide with catalogue DB IDs and survive JS JSON.
    return -int(
        hashlib.sha256(f"{asset}:{start}:{end}:{text}".encode()).hexdigest()[:13], 16
    )


def story_passages(segments: list[dict]) -> list[dict]:
    """Split only with verified word timings; join close unfinished continuations.

    Punctuation is a boundary hint, never proof of semantic completeness. Missing
    timings keep the original text/time range, with uncertainty made explicit.
    """
    units = []
    for raw in sorted(
        segments, key=lambda s: (str(s["asset_id"]), float(s["start_seconds"]))
    ):
        segment = deepcopy(raw)
        words = _words(segment)
        groups = []
        if words:
            group = []
            for word in words:
                group.append(word)
                if _END.search(word["text"]):
                    groups.append(group)
                    group = []
            if group:
                groups.append(group)
        if not groups:
            segment.pop("words", None)
            segment["boundary_evidence"] = "catalogue_only"
            units.append(segment)
            continue
        for group in groups:
            text = " ".join(w["text"] for w in group)
            prefix = _PREFIX.match(text)
            if prefix:
                offset, keep = 0, []
                for word in group:
                    if offset >= prefix.end():
                        keep.append(word)
                    offset += len(word["text"]) + 1
                if keep:
                    group = keep
                    text = " ".join(w["text"] for w in group)
            start, end = group[0]["start"], group[-1]["end"]
            same = (
                start == float(raw["start_seconds"])
                and end == float(raw["end_seconds"])
                and text == str(raw["text"]).strip()
            )
            units.append(
                {
                    **segment,
                    "id": int(raw["id"])
                    if same
                    else _identity(str(raw["asset_id"]), start, end, text),
                    "start_seconds": start,
                    "end_seconds": end,
                    "text": text,
                    "catalogue_ids": [int(raw["id"])],
                    "boundary_evidence": "word_timed",
                }
            )
    result = []
    for unit in units:
        unit.pop("words", None)
        previous = result[-1] if result else None
        if (
            previous
            and str(previous["asset_id"]) == str(unit["asset_id"])
            and not _END.search(previous["text"].strip())
            and 0
            <= float(unit["start_seconds"]) - float(previous["end_seconds"])
            <= 0.65
            and float(unit["end_seconds"]) - float(previous["start_seconds"]) <= 25
            and len(previous["text"]) + len(unit["text"]) < 850
        ):
            previous["text"] += " " + unit["text"]
            previous["end_seconds"] = unit["end_seconds"]
            previous["catalogue_ids"] = list(
                dict.fromkeys(
                    previous.get("catalogue_ids", [previous["id"]])
                    + unit.get("catalogue_ids", [unit["id"]])
                )
            )
            previous["id"] = _identity(
                str(previous["asset_id"]),
                previous["start_seconds"],
                previous["end_seconds"],
                previous["text"],
            )
            previous["boundary_evidence"] = "joined_continuation"
        else:
            result.append(unit)
    for unit in result:
        text = unit["text"].strip()
        unit["sentence_end"] = bool(_END.search(text))
        unit["needs_context"] = (
            bool(re.match(r"^(?:because|and|but|which)\b", text, re.I))
            or not unit["sentence_end"]
        )
    return result
