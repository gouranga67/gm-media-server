"""Conservative transcript-backed checks for explicit brief structure."""

from collections import Counter
import math
import re
from typing import Any


_WORD = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "our", "the", "their", "this", "to", "we",
    "with", "you", "your",
}
_CRITICAL = {"no", "not", "never", "without", "only", "but", "because", "cannot"}


def _tokens(value: str, *, keywords: bool = False) -> list[str]:
    result = _WORD.findall(str(value or "").lower().replace("’", "'"))
    return [token for token in result if not keywords or token not in _STOPWORDS]


def _asset_tokens(asset: dict[str, Any]) -> list[str]:
    words = []
    fallback = []
    for segment in asset.get("transcript_segments", []):
        segment_words = [
            str(word.get("text", word.get("word", "")))
            for word in segment.get("words", [])
            if isinstance(word, dict)
        ]
        if segment_words:
            words.extend(segment_words)
        else:
            fallback.append(str(segment.get("text") or ""))
    return _tokens(" ".join(words + fallback))


def _selected_tokens(plan: Any, assets: list[dict[str, Any]]) -> list[str]:
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    selected = []
    for clip in plan.clips:
        if getattr(clip, "media_kind", "video") != "video":
            continue
        if hasattr(clip, "include_source_audio") and not clip.include_source_audio:
            continue
        left, right = float(clip.source_in), float(clip.source_out)
        asset = inventory.get(str(clip.asset_id), {})
        for segment in asset.get("transcript_segments", []):
            timed_words = []
            has_timed_words = False
            for word in segment.get("words", []):
                try:
                    start, end = float(word["start"]), float(word["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not math.isfinite(start + end) or start >= end:
                    continue
                has_timed_words = True
                if left <= (start + end) / 2 < right:
                    timed_words.append(str(word.get("text", word.get("word", ""))))
            if has_timed_words:
                selected.extend(_tokens(" ".join(timed_words)))
                continue
            try:
                start, end = float(segment["start"]), float(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            overlap = max(0.0, min(right, end) - max(left, start))
            if end > start and overlap / (end - start) >= 0.6:
                selected.extend(_tokens(str(segment.get("text") or "")))
    return selected


def _bag_coverage(required: list[str], available: list[str]) -> float:
    if not required:
        return 1.0
    wanted, found = Counter(required), Counter(available)
    return sum(min(count, found[token]) for token, count in wanted.items()) / len(required)


def _lcs_coverage(required: list[str], actual: list[str]) -> float:
    if not required:
        return 1.0
    if not actual:
        return 0.0
    row = [0] * (len(actual) + 1)
    for expected in required:
        previous = 0
        for index, observed in enumerate(actual, 1):
            saved = row[index]
            row[index] = previous + 1 if expected == observed else max(row[index], row[index - 1])
            previous = saved
    return row[-1] / len(required)


def _ordered_match(required: list[str], actual: list[str], start: int) -> tuple[float, int]:
    if not required:
        return 1.0, start
    cursor, matched = start, 0
    for token in required:
        try:
            cursor = actual.index(token, cursor) + 1
            matched += 1
        except ValueError:
            continue
    return matched / len(required), cursor


def check_brief_contract(
    plan: Any,
    contract: dict[str, Any] | None,
    assets: list[dict[str, Any]],
    *,
    enforce: bool = True,
) -> dict[str, Any]:
    """Check only claims supported by transcript evidence.

    Visual scene meaning still needs human review. A plan is rejected only when
    the sources clearly support an instruction and the selected speech omits or
    reorders it.
    """
    if not contract or not contract.get("required_items"):
        return {"version": 1, "status": "not_applicable", "checks": [],
                "findings": [], "semantic_judgement": "human_review_required", "hosted_model_calls": 0}
    mode = str(contract.get("instruction_mode") or "creative_brief")
    items = [str(item) for item in contract.get("required_items", []) if str(item).strip()]
    inventory = [token for asset in assets for token in _asset_tokens(asset)]
    selected = _selected_tokens(plan, assets)
    checks: list[dict[str, Any]] = []
    problems: list[str] = []

    if mode == "supplied_script":
        required = _tokens(" ".join(items))
        source_coverage = _bag_coverage(required, inventory)
        selected_coverage = _lcs_coverage(required, selected)
        critical = [
            token for index, token in enumerate(required)
            if index in {0, len(required) - 1}
            or token in _CRITICAL
            or any(char.isdigit() for char in token)
        ]
        critical_present = _bag_coverage(critical, selected) == 1.0 if critical else True
        source_supported = len(required) >= 3 and source_coverage >= 0.75
        present = source_supported and selected_coverage >= 0.85 and critical_present
        checks.append({
            "item": 1,
            "kind": "script",
            "source_supported": source_supported,
            "present": present,
            "in_order": present,
            "source_word_coverage": round(source_coverage, 3),
            "selected_word_coverage": round(selected_coverage, 3),
        })
        if source_supported and not present:
            problems.append("the selected speech does not preserve the complete supplied script in order")
        elif not source_supported:
            problems.append("the supplied script could not be verified against the available transcript")
        if enforce and source_supported and not present:
            raise ValueError(
                "brief contract: the recordings support the supplied script, but the proposed edit omits, "
                "changes or reorders required wording. Preserve the complete script and its ending."
            )
    else:
        cursor = 0
        for index, item in enumerate(items, 1):
            required = _tokens(item, keywords=True)
            source_coverage = _bag_coverage(required, inventory)
            source_supported = len(required) >= 2 and source_coverage >= 0.7
            ordered_coverage, next_cursor = _ordered_match(required, selected, cursor)
            anywhere_coverage, _ = _ordered_match(required, selected, 0)
            present = source_supported and anywhere_coverage >= 0.7
            in_order = present and ordered_coverage >= 0.7
            checks.append({
                "item": index,
                "kind": "scene" if mode == "ordered_scenes" else "point",
                "source_supported": source_supported,
                "present": present,
                "in_order": in_order,
                "source_word_coverage": round(source_coverage, 3),
            })
            if source_supported and not present:
                problems.append(f"required item {index} is missing from the selected speech")
            elif source_supported and not in_order:
                problems.append(f"required item {index} appears out of order")
            if in_order:
                cursor = next_cursor
        enforceable = [check for check in checks if check["source_supported"]]
        if enforce and any(not check["present"] or not check["in_order"] for check in enforceable):
            raise ValueError(
                "brief contract: transcript-supported scenes or points are missing or out of order. "
                "Include every supported item in the user's supplied order."
            )
        if len(enforceable) < len(checks):
            problems.append("some visual or semantic instructions still require human review")

    status = "checked" if checks and not problems else "attention"
    return {
        "version": 1,
        "status": status,
        "instruction_mode": mode,
        "checks": checks,
        "findings": problems,
        "semantic_judgement": "human_review_required",
        "hosted_model_calls": 0,
    }
