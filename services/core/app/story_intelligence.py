import re
from typing import Any

from app.config import Settings, get_settings
from app.content_catalog import _transcript_segments


STORY_INTELLIGENCE_VERSION = "1.0"
MAX_STORED_MOMENTS = 120
MAX_CONTEXT_MOMENTS = 24

_WORD = re.compile(r"[a-z0-9']+")
_HOOK_WORDS = {
    "how", "why", "what", "secret", "surprise", "never", "best", "worst",
    "first", "imagine", "watch", "listen", "problem",
}
_PAYOFF_WORDS = {
    "because", "therefore", "result", "finally", "actually", "so", "learned",
    "realized", "worked", "answer", "difference",
}
_ENDING_WORDS = {
    "follow", "subscribe", "share", "comment", "try", "remember", "today",
    "next", "thanks", "thank", "visit", "join",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _tokens(value: str) -> set[str]:
    return set(_WORD.findall(value.lower()))


def _roles_for_spoken_moment(text: str, position: float) -> tuple[list[str], list[str], float]:
    words = _tokens(text)
    signals: list[str] = []
    roles: list[str] = []
    score = 0.45
    if "?" in text or words & _HOOK_WORDS:
        signals.append("curiosity_or_question")
        roles.append("hook")
        score += 0.2
    if "!" in text:
        signals.append("verbal_emphasis")
        roles.extend(("hook", "reaction"))
        score += 0.1
    if words & _PAYOFF_WORDS:
        signals.append("explanation_or_payoff")
        roles.extend(("development", "payoff"))
        score += 0.15
    if words & _ENDING_WORDS:
        signals.append("ending_or_action_language")
        roles.append("ending")
        score += 0.15
    if position <= 0.2:
        signals.append("early_in_source")
        roles.extend(("hook", "context"))
        score += 0.08
    elif position >= 0.75:
        signals.append("late_in_source")
        roles.extend(("payoff", "ending"))
        score += 0.08
    else:
        roles.extend(("context", "development"))
    if len(words) >= 5:
        signals.append("complete_spoken_thought")
        score += 0.07
    return list(dict.fromkeys(roles))[:3], signals, min(1.0, score)


def build_story_moments(
    asset: dict[str, Any],
    manifest: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Build compact narrative evidence from local, source-timestamped facts."""

    settings = settings or get_settings()
    probe = manifest.get("probe") if isinstance(manifest.get("probe"), dict) else {}
    probe_format = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    duration = _number(probe_format.get("duration_seconds"))
    mime_type = str(asset.get("mime_type") or "")
    moments: list[dict[str, Any]] = []

    for index, raw in enumerate(_transcript_segments(settings, manifest)):
        if not isinstance(raw, dict):
            continue
        text = " ".join(str(raw.get("text") or "").split())
        start = _number(raw.get("start"))
        end = max(start, _number(raw.get("end"), start))
        if not text or end <= start:
            continue
        position = start / duration if duration > 0 else 0.0
        roles, signals, score = _roles_for_spoken_moment(text, position)
        moments.append(
            {
                "moment_id": f"spoken-{index}",
                "kind": "spoken",
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": text[:1200],
                "signals": signals,
                "suggested_roles": roles,
                "intrinsic_score": round(score, 3),
                "evidence": ["faster-whisper-small"],
            }
        )

    boundaries = manifest.get("derived", {}).get("scene_boundaries_seconds", [])
    clean_boundaries = sorted(
        {round(_number(value), 3) for value in boundaries if 0 < _number(value) < duration}
    ) if isinstance(boundaries, list) else []
    if mime_type.startswith("video/") and duration > 0:
        points = [0.0, *clean_boundaries, round(duration, 3)]
        for index, (start, end) in enumerate(zip(points, points[1:])):
            if end - start < 0.25:
                continue
            position = start / duration
            roles = ["context", "development"]
            if position <= 0.15:
                roles = ["hook", "context"]
            elif position >= 0.8:
                roles = ["payoff", "ending"]
            moments.append(
                {
                    "moment_id": f"scene-{index}",
                    "kind": "visual_window",
                    "start_seconds": start,
                    "end_seconds": end,
                    "text": "Source-derived scene window",
                    "signals": ["scene_boundary_window"],
                    "suggested_roles": roles,
                    "intrinsic_score": 0.4,
                    "evidence": ["ffmpeg-scene-detect"],
                }
            )
    elif mime_type.startswith("image/"):
        moments.append(
            {
                "moment_id": "still-0",
                "kind": "still",
                "start_seconds": 0.0,
                "end_seconds": 0.0,
                "text": "Source still image",
                "signals": ["still_image"],
                "suggested_roles": ["context", "development", "payoff"],
                "intrinsic_score": 0.4,
                "evidence": ["ffprobe"],
            }
        )
    return moments[:MAX_STORED_MOMENTS]


def select_story_moments(
    moments: list[dict[str, Any]],
    query: str,
    limit: int = MAX_CONTEXT_MOMENTS,
) -> list[dict[str, Any]]:
    """Retrieve relevant moments locally while retaining opening and ending evidence."""

    if not moments or limit <= 0:
        return []
    query_tokens = _tokens(query)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    spoken_indexes: list[int] = []
    for index, moment in enumerate(moments):
        text_tokens = _tokens(str(moment.get("text") or ""))
        overlap = len(query_tokens & text_tokens)
        relevance = overlap / max(1, len(query_tokens))
        intrinsic = float(moment.get("intrinsic_score") or 0)
        score = intrinsic + relevance * 1.5
        if moment.get("kind") == "spoken":
            spoken_indexes.append(index)
        scored.append((score, index, moment))

    required = set()
    if spoken_indexes:
        required.update((spoken_indexes[0], spoken_indexes[-1]))
    ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
    selected_indexes = set(required)
    for _, index, _ in ranked:
        if len(selected_indexes) >= limit:
            break
        selected_indexes.add(index)

    selected: list[dict[str, Any]] = []
    scores = {index: score for score, index, _ in scored}
    for index in sorted(selected_indexes, key=lambda value: (-scores[value], value)):
        moment = dict(moments[index])
        moment["retrieval_score"] = round(scores[index], 3)
        selected.append(moment)
    return selected[:limit]
