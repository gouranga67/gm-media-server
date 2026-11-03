"""Word-timed incident windows for discovery, not a judgement of comic quality."""

import math
import re
from copy import deepcopy

from app.blooper_detection import (
    _CLUES,
    find_blooper_evidence,
    has_specific_blooper_clue,
    QUESTION_UNCERTAINTY_PATTERN,
)


def _words(segment: dict) -> list[dict]:
    start, end = float(segment["start_seconds"]), float(segment["end_seconds"])
    result = []
    for raw in segment.get("words") or []:
        try:
            left, right = float(raw["start"]), float(raw["end"])
        except (ValueError, TypeError, KeyError):
            continue
        text = str(raw.get("word") or raw.get("text") or "").strip()
        if (
            not text
            or not math.isfinite(left + right)
            or right <= left
            or left < 0
            or left < start - 0.03
            or right > end + 0.03
        ):
            continue
        if result and left < result[-1]["end"] - 0.03:
            return []
        result.append({"start": left, "end": right, "text": text})

    # Don't construct precise clips from incomplete or unrelated word timings.
    def normalize(text):
        return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))

    if normalize(" ".join(word["text"] for word in result)) != normalize(
        str(segment.get("text") or "")
    ):
        return []
    return result


def _range(segment: dict, words: list[dict], left: int, right: int) -> dict:
    selected = words[left : right + 1]
    return {
        "start": selected[0]["start"],
        "end": selected[-1]["end"],
        "text": " ".join(word["text"] for word in selected),
        "blooper_scope_version": 1,
        "catalog_range": {
            "start": float(segment["start_seconds"]),
            "end": float(segment["end_seconds"]),
        },
    }


def focus_blooper_passages(
    segments: list[dict], clues: dict[int, dict]
) -> dict[int, dict]:
    """Keep short clause-bounded incidents and nearby context from each recording.

    Catalogue chunks can contain a whole pitch. Word timings let us offer an
    actual stumble instead of obliging the concept producer to quote that pitch.
    When timing is unavailable, only already-short passages remain selectable.
    No interpolated timestamps, new ASR, generated dialogue or forced retiming.
    """
    focused = {}
    by_id = {int(segment["id"]): segment for segment in segments}
    for identity, clue in clues.items():
        if not has_specific_blooper_clue(clue):
            continue
        segment = by_id[identity]
        words = _words(segment)
        if not words:
            if float(segment["end_seconds"]) - float(segment["start_seconds"]) <= 8:
                focused[identity] = {
                    "start": float(segment["start_seconds"]),
                    "end": float(segment["end_seconds"]),
                    "text": str(segment["text"]),
                    "blooper_scope_version": 1,
                    "incident": {
                        "start": float(segment["start_seconds"]),
                        "end": float(segment["end_seconds"]),
                    },
                }
            continue
        text, offsets = "", []
        for word in words:
            offsets.append((len(text), len(text) + len(word["text"])))
            text += word["text"] + " "
        matches = [
            match
            for pattern, reason in _CLUES
            if reason in clue["blooper_signals"]
            for match in re.finditer(pattern, text.lower().replace("’", "'"))
        ]
        if not matches:
            continue
        match = min(matches, key=lambda item: item.start())
        first = next(
            (i for i, (_, end) in enumerate(offsets) if end > match.start()), None
        )
        last = next(
            (i for i, (_, end) in enumerate(offsets) if end >= match.end()), None
        )
        if first is None or last is None:
            continue
        # Start at a genuine clause boundary within six seconds before the clue.
        # No boundary is safer than starting in the middle of somebody's phrase.
        candidates = [
            i
            for i in range(first + 1)
            if words[first]["start"] - words[i]["start"] <= 6
            and (i == 0 or re.search(r"[,.;!?]$", words[i - 1]["text"]))
        ]
        if not candidates:
            continue
        left = min(candidates)
        right = last
        # Finish the spoken reaction, without absorbing the next product list.
        while right + 1 < len(words) and not re.search(
            r"[,.;!?]$", words[right]["text"]
        ):
            if words[right + 1]["end"] - words[last]["end"] > 2:
                break
            right += 1
        if right + 1 < len(words) and not re.search(r"[,.;!?]$", words[right]["text"]):
            continue
        if words[right]["end"] - words[left]["start"] > 10:
            continue
        focused[identity] = {
            **_range(segment, words, left, right),
            "incident": {"start": words[first]["start"], "end": words[last]["end"]},
        }
    # Neighbouring setup/recovery remains available, but never a whole long take.
    for identity, clue in clues.items():
        if has_specific_blooper_clue(clue) or identity in focused:
            continue
        segment = by_id[identity]
        nearby = [
            window
            for other_id, window in focused.items()
            if window.get("incident")
            and str(by_id[other_id]["asset_id"]) == str(segment["asset_id"])
        ]
        before = any(
            0 <= window["start"] - float(segment["end_seconds"]) <= 6
            for window in nearby
        )
        after = any(
            0 <= float(segment["start_seconds"]) - window["end"] <= 2
            for window in nearby
        )
        if not before and not after:
            continue
        words = _words(segment)
        if not words:
            if float(segment["end_seconds"]) - float(segment["start_seconds"]) <= 4:
                focused[identity] = {
                    "start": float(segment["start_seconds"]),
                    "end": float(segment["end_seconds"]),
                    "text": str(segment["text"]),
                    "blooper_scope_version": 1,
                }
            continue
        if after:
            ends = [
                i
                for i, word in enumerate(words)
                if word["end"] - words[0]["start"] <= 4
                and re.search(r"[,.;!?]$", word["text"])
            ]
            if ends:
                focused[identity] = _range(segment, words, 0, max(ends))
        else:
            starts = [
                i
                for i, word in enumerate(words)
                if words[-1]["end"] - word["start"] <= 4
                and (i == 0 or re.search(r"[,.;!?]$", words[i - 1]["text"]))
            ]
            if starts:
                focused[identity] = _range(segment, words, min(starts), len(words) - 1)
    return focused


def attach_word_times(rows: list[dict], segments: list[dict], *, all_sources: bool = False, include_long_incidents: bool = False) -> list[dict]:
    """Read only existing transcript derivatives, and keep timings local."""
    from app.content_catalog import _transcript_segments
    from app.config import get_settings

    clues = find_blooper_evidence(segments)
    candidates = {
        str(segment["asset_id"])
        for segment in segments
        if all_sources or has_specific_blooper_clue(clues.get(int(segment["id"]), {})) or (
            include_long_incidents and any(re.search(pattern, str(segment.get("text") or "").lower().replace("’", "'"))
                for pattern in [*(p for p, r in _CLUES if r != "transcribed_laughter"), QUESTION_UNCERTAINTY_PATTERN]))
    }
    if not candidates:
        return deepcopy(segments)
    settings = get_settings()
    timed = {}
    for row in rows:
        if str(row["id"]) not in candidates:
            continue
        try:
            transcript = _transcript_segments(settings, row.get("manifest") or {})
        except (OSError, ValueError, TypeError):
            transcript = []
        valid = []
        for piece in transcript:
            if not isinstance(piece, dict) or not isinstance(piece.get("words"), list):
                continue
            for word in piece["words"]:
                if not isinstance(word, dict):
                    continue
                try:
                    start, end = float(word["start"]), float(word["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(start + end) and 0 <= start < end:
                    valid.append({**word, "start": start, "end": end})
        timed[str(row["id"])] = valid
    result = deepcopy(segments)
    for segment in result:
        segment["words"] = [
            word
            for word in timed.get(str(segment["asset_id"]), [])
            if word["start"] >= float(segment["start_seconds"]) - 0.03
            and word["end"] <= float(segment["end_seconds"]) + 0.03
        ]
    return result


def selected_blooper_scope(context: dict) -> list[dict]:
    selected = context.get("selected_concept") or {}
    script = selected.get("script") or []
    if (
        selected.get("reel_kind") != "bloopers"
        or not script
        or not all(beat.get("blooper_scope_version") == 1 for beat in script)
    ):
        return []
    return [
        {
            "asset_id": str(beat["asset_id"]),
            "start": float(beat["start"]),
            "end": float(beat["end"]),
            "incident": beat.get("incident"),
            **({"required_ranges": [beat["setup"], beat["incident"], beat["reaction"]]}
               if beat.get("incident_id") and beat.get("setup") and beat.get("reaction") else {}),
        }
        for beat in script
    ]


def validate_blooper_scope(plan, direction: dict) -> None:
    scope = direction.get("selected_blooper_scope") or []
    if not scope:
        return
    for clip in plan.clips:
        windows = sorted(
            (item["start"] - 0.35, item["end"] + 0.35)
            for item in scope
            if str(item["asset_id"]) == str(clip.asset_id)
        )
        cursor = float(clip.source_in)
        for left, right in windows:
            if left > cursor + 0.01:
                break
            cursor = max(cursor, right)
            if cursor >= float(clip.source_out) - 0.01:
                break
        if cursor < float(clip.source_out) - 0.01:
            raise ValueError(
                "blooper edit extends beyond the selected incident/setup/reaction; omit unrelated sales introduction or product-list recovery"
            )

    for item in scope:
        for anchor in item.get("required_ranges") or [item.get("incident")]:
            if not anchor:
                continue
            covered = sum(
                max(
                    0,
                    min(float(clip.source_out), anchor["end"])
                    - max(float(clip.source_in), anchor["start"]),
                )
                for clip in plan.clips
                if str(clip.asset_id) == str(item["asset_id"])
            )
            if covered < max(0.01, anchor["end"] - anchor["start"] - 0.1):
                raise ValueError(
                    "blooper edit omitted the selected recorded incident/setup/reaction; keep the actual attempt and response together"
                )
