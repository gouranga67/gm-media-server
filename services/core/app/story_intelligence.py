import re
from typing import Any

from app.config import Settings, get_settings
from app.content_catalog import _transcript_segments
from app.take_quality import production_chatter_reason


STORY_INTELLIGENCE_VERSION = "1.1"
MAX_STORED_MOMENTS = 120
MAX_CONTEXT_MOMENTS = 24

_WORD = re.compile(r"[a-z0-9']+")
_NUMBER = re.compile(r"(?:^|\s)(?:\d[\d,.]*|\d+%)(?:\s|$)")
_HOOK_WORDS = {
    "how", "why", "what", "secret", "surprise", "never", "best", "worst",
    "first", "imagine", "watch", "listen", "problem", "mistake", "truth",
}
_PAYOFF_WORDS = {
    "because", "therefore", "result", "finally", "actually", "so", "learned",
    "realized", "worked", "answer", "difference", "changed", "solved",
}
_ENDING_WORDS = {
    "follow", "subscribe", "share", "comment", "try", "remember", "today",
    "next", "thanks", "thank", "visit", "join",
}
_CONTRAST_WORDS = {
    "but", "however", "instead", "although", "yet", "except", "versus", "unlike",
}
_REACTION_WORDS = {
    "amazing", "awesome", "wow", "love", "hate", "funny", "laugh", "shocked",
    "surprised", "unbelievable", "incredible", "scary", "beautiful",
}
_ROLE_ORDER = ("hook", "context", "development", "payoff", "reaction", "ending")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _tokens(value: str) -> set[str]:
    return set(_WORD.findall(value.lower()))


def _word_list(value: str) -> list[str]:
    return _WORD.findall(value.lower())


def _mean_word_confidence(raw: dict[str, Any]) -> float | None:
    words = raw.get("words")
    if not isinstance(words, list):
        return None
    probabilities = [
        float(word["probability"])
        for word in words
        if isinstance(word, dict) and isinstance(word.get("probability"), (int, float))
    ]
    return round(sum(probabilities) / len(probabilities), 3) if probabilities else None


def _spoken_analysis(
    text: str,
    *,
    position: float,
    duration: float,
    pause_before: float,
    pause_after: float,
    confidence: float | None,
) -> tuple[list[str], list[str], dict[str, float], dict[str, float], dict[str, Any], float]:
    words = _word_list(text)
    token_set = set(words)
    word_count = len(words)
    speech_rate = word_count / max(duration, 0.25)
    signals: list[str] = []
    role_scores = {role: 0.05 for role in _ROLE_ORDER}
    role_scores["development"] = 0.35
    role_scores["context"] = 0.22

    if "?" in text or token_set & _HOOK_WORDS:
        signals.append("curiosity_or_question")
        role_scores["hook"] += 0.58
    if "!" in text:
        signals.append("verbal_emphasis")
        role_scores["hook"] += 0.18
        role_scores["reaction"] += 0.32
    if token_set & _CONTRAST_WORDS:
        signals.append("contrast_or_turn")
        role_scores["development"] += 0.24
        role_scores["payoff"] += 0.16
    if token_set & _PAYOFF_WORDS:
        signals.append("explanation_or_payoff")
        role_scores["development"] += 0.24
        role_scores["payoff"] += 0.48
    if token_set & _REACTION_WORDS:
        signals.append("emotional_or_reaction_language")
        role_scores["reaction"] += 0.48
        role_scores["hook"] += 0.10
    if token_set & _ENDING_WORDS:
        signals.append("ending_or_action_language")
        role_scores["ending"] += 0.62
    if _NUMBER.search(f" {text} "):
        signals.append("specific_number_or_measure")
        role_scores["hook"] += 0.12
        role_scores["payoff"] += 0.12
    if position <= 0.2:
        signals.append("early_in_source")
        role_scores["hook"] += 0.14
        role_scores["context"] += 0.18
    elif position >= 0.75:
        signals.append("late_in_source")
        role_scores["payoff"] += 0.15
        role_scores["ending"] += 0.22
    else:
        role_scores["development"] += 0.12

    complete_thought = word_count >= 5 and (text.rstrip().endswith((".", "?", "!")) or word_count >= 9)
    if complete_thought:
        signals.append("complete_spoken_thought")
    if pause_before >= 0.18:
        signals.append("clean_cut_in")
    if pause_after >= 0.18:
        signals.append("clean_cut_out")
    if 1.4 <= speech_rate <= 3.4:
        signals.append("clear_speech_cadence")
    elif speech_rate > 4.2:
        signals.append("fast_speech_cadence")
    elif speech_rate < 0.9 and word_count >= 3:
        signals.append("slow_speech_cadence")

    clarity = 0.36
    clarity += 0.22 if complete_thought else 0
    clarity += 0.16 if 1.2 <= speech_rate <= 3.8 else 0
    clarity += 0.12 if confidence is not None and confidence >= 0.82 else 0
    clarity += 0.08 if word_count >= 5 else 0
    editability = 0.36
    editability += 0.2 if pause_before >= 0.18 else 0
    editability += 0.2 if pause_after >= 0.18 else 0
    editability += 0.16 if complete_thought else 0
    specificity = 0.18
    specificity += 0.28 if _NUMBER.search(f" {text} ") else 0
    specificity += min(0.28, len(token_set) / 60)
    hook = role_scores["hook"]
    payoff = role_scores["payoff"]
    reaction = role_scores["reaction"]
    engagement = _clamp(
        0.25 * _clamp(hook)
        + 0.20 * _clamp(payoff)
        + 0.12 * _clamp(reaction)
        + 0.18 * _clamp(clarity)
        + 0.15 * _clamp(editability)
        + 0.10 * _clamp(specificity)
    )
    components = {
        "hook": round(_clamp(hook), 3),
        "payoff": round(_clamp(payoff), 3),
        "reaction": round(_clamp(reaction), 3),
        "clarity": round(_clamp(clarity), 3),
        "editability": round(_clamp(editability), 3),
        "specificity": round(_clamp(specificity), 3),
    }
    normalized_role_scores = {
        role: round(_clamp(score), 3) for role, score in role_scores.items()
    }
    ordered_roles = sorted(_ROLE_ORDER, key=lambda role: (-role_scores[role], _ROLE_ORDER.index(role)))
    roles = ordered_roles[:3]
    edit_guidance = {
        "pause_before_seconds": round(pause_before, 3),
        "pause_after_seconds": round(pause_after, 3),
        "speech_rate_words_per_second": round(speech_rate, 3),
        "word_count": word_count,
        "preserves_complete_thought": complete_thought,
        "clean_cut_in": pause_before >= 0.18,
        "clean_cut_out": pause_after >= 0.18,
        "audio_bridge_candidate": pause_before < 0.12 or pause_after < 0.12,
    }
    return roles, signals, normalized_role_scores, components, edit_guidance, engagement


def build_story_moments(
    asset: dict[str, Any],
    manifest: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Build reusable engagement and narrative evidence from local source facts."""

    settings = settings or get_settings()
    probe = manifest.get("probe") if isinstance(manifest.get("probe"), dict) else {}
    probe_format = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    source_duration = _number(probe_format.get("duration_seconds"))
    mime_type = str(asset.get("mime_type") or "")
    moments: list[dict[str, Any]] = []
    transcript = [item for item in _transcript_segments(settings, manifest) if isinstance(item, dict)]

    for index, raw in enumerate(transcript):
        text = " ".join(str(raw.get("text") or "").split())
        start = _number(raw.get("start"))
        end = max(start, _number(raw.get("end"), start))
        if not text or end <= start:
            continue
        previous_end = _number(transcript[index - 1].get("end")) if index else 0.0
        next_start = (
            _number(transcript[index + 1].get("start"), source_duration)
            if index + 1 < len(transcript)
            else source_duration
        )
        pause_before = max(0.0, start - previous_end)
        pause_after = max(0.0, next_start - end)
        position = start / source_duration if source_duration > 0 else 0.0
        confidence = _mean_word_confidence(raw)
        roles, signals, role_scores, components, guidance, engagement = _spoken_analysis(
            text,
            position=position,
            duration=end - start,
            pause_before=pause_before,
            pause_after=pause_after,
            confidence=confidence,
        )
        moment = {
            "moment_id": f"spoken-{index}",
            "kind": "spoken",
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "text": text[:1200],
            "signals": signals,
            "suggested_roles": roles,
            "role_scores": role_scores,
            "engagement_score": round(engagement, 3),
            "score_components": components,
            "edit_guidance": guidance,
            "intrinsic_score": round(_clamp(0.36 + engagement * 0.64), 3),
            "evidence": ["faster-whisper-small", "local-cadence-analysis-v1"],
        }
        if confidence is not None:
            moment["transcript_confidence"] = confidence
        moments.append(moment)

    derived = manifest.get("derived") if isinstance(manifest.get("derived"), dict) else {}
    boundaries = derived.get("scene_boundaries_seconds", [])
    clean_boundaries = sorted(
        {round(_number(value), 3) for value in boundaries if 0 < _number(value) < source_duration}
    ) if isinstance(boundaries, list) else []
    quality = derived.get("visual_quality") if isinstance(derived.get("visual_quality"), dict) else {}
    sharpness = _number(quality.get("mean_sharpness_score"))
    quality_measured = quality.get("status") == "measured"
    if mime_type.startswith("video/") and source_duration > 0:
        points = [0.0, *clean_boundaries, round(source_duration, 3)]
        for index, (start, end) in enumerate(zip(points, points[1:])):
            scene_duration = end - start
            if scene_duration < 0.25:
                continue
            position = start / source_duration
            roles = ["context", "development"]
            if position <= 0.15:
                roles = ["hook", "context"]
            elif position >= 0.8:
                roles = ["payoff", "ending"]
            pace = "fast" if scene_duration <= 2.5 else "medium" if scene_duration <= 6 else "hold"
            signals = ["scene_boundary_window", f"{pace}_visual_pace"]
            if quality_measured:
                signals.append("measured_visual_sharpness")
            engagement = _clamp(0.34 + (0.16 if pace == "fast" else 0.08 if pace == "medium" else 0))
            moments.append(
                {
                    "moment_id": f"scene-{index}",
                    "kind": "visual_window",
                    "start_seconds": start,
                    "end_seconds": end,
                    "text": "Source-derived scene window",
                    "signals": signals,
                    "suggested_roles": roles,
                    "role_scores": {role: round(0.65 if role in roles else 0.08, 3) for role in _ROLE_ORDER},
                    "engagement_score": round(engagement, 3),
                    "score_components": {
                        "visual_pace": 0.75 if pace == "fast" else 0.58 if pace == "medium" else 0.38,
                        "sharpness": round(sharpness, 3) if quality_measured else None,
                    },
                    "edit_guidance": {
                        "visual_pace": pace,
                        "scene_duration_seconds": round(scene_duration, 3),
                        "cut_on_scene_boundary": True,
                    },
                    "intrinsic_score": round(engagement, 3),
                    "evidence": ["ffmpeg-scene-detect", "ffmpeg-edge-energy-v1"],
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
                "signals": ["still_image"] + (["measured_visual_sharpness"] if quality_measured else []),
                "suggested_roles": ["context", "development", "payoff"],
                "role_scores": {role: (0.55 if role in {"context", "development", "payoff"} else 0.08) for role in _ROLE_ORDER},
                "engagement_score": 0.38,
                "score_components": {"sharpness": round(sharpness, 3) if quality_measured else None},
                "edit_guidance": {"visual_pace": "hold", "recommended_duration_seconds": 3.0},
                "intrinsic_score": 0.4,
                "evidence": ["ffprobe", "ffmpeg-edge-energy-v1"],
            }
        )
    return moments[:MAX_STORED_MOMENTS]


def _similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = _tokens(str(left.get("text") or ""))
    right_tokens = _tokens(str(right.get("text") or ""))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def select_story_moments(
    moments: list[dict[str, Any]],
    query: str,
    limit: int = MAX_CONTEXT_MOMENTS,
    *,
    preserve_outtakes: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve relevant, structurally useful moments while suppressing repetition."""

    if not moments or limit <= 0:
        return []
    # Re-evaluate stored moments at retrieval time too: existing libraries must
    # benefit without paying for transcription or requiring a full re-index.
    moments = [dict(moment) for moment in moments]
    for moment in moments:
        reason = production_chatter_reason(str(moment.get("text") or ""))
        if not preserve_outtakes and moment.get("kind") == "spoken" and reason is not None and reason != "possible_script_discussion":
            moment["signals"] = [*(moment.get("signals") or []), "production_chatter"]
            moment["role_scores"] = {role: 0.0 for role in _ROLE_ORDER}
            moment["suggested_roles"] = []
            moment["engagement_score"] = 0.0
            moment["intrinsic_score"] = 0.02
    query_tokens = _tokens(query)
    base_scores: dict[int, float] = {}
    spoken_indexes: list[int] = []
    for index, moment in enumerate(moments):
        text_tokens = _tokens(str(moment.get("text") or ""))
        overlap = len(query_tokens & text_tokens)
        relevance = overlap / max(1, len(query_tokens))
        intrinsic = float(moment.get("intrinsic_score") or 0)
        engagement = float(moment.get("engagement_score") or 0)
        base_scores[index] = intrinsic + engagement * 0.35 + relevance * 1.5
        if preserve_outtakes and production_chatter_reason(str(moment.get("text") or "")):
            base_scores[index] += 1.0
        if moment.get("kind") == "spoken" and "production_chatter" not in (moment.get("signals") or []):
            spoken_indexes.append(index)

    selected_indexes: list[int] = []
    for required in ([spoken_indexes[0], spoken_indexes[-1]] if spoken_indexes else []):
        if required not in selected_indexes and len(selected_indexes) < limit:
            selected_indexes.append(required)
    remaining = set(range(len(moments))) - set(selected_indexes)
    while remaining and len(selected_indexes) < limit:
        best_index = max(
            remaining,
            key=lambda index: (
                base_scores[index]
                - (0 if preserve_outtakes else 0.65) * max((_similarity(moments[index], moments[chosen]) for chosen in selected_indexes), default=0),
                -index,
            ),
        )
        selected_indexes.append(best_index)
        remaining.remove(best_index)

    selected: list[dict[str, Any]] = []
    for index in sorted(selected_indexes, key=lambda value: (-base_scores[value], value)):
        moment = dict(moments[index])
        moment["retrieval_score"] = round(base_scores[index], 3)
        reasons: list[str] = []
        if query_tokens & _tokens(str(moment.get("text") or "")):
            reasons.append("matches_story_direction")
        if float(moment.get("engagement_score") or 0) >= 0.55:
            reasons.append("strong_local_engagement_signals")
        if set(moment.get("suggested_roles") or []) & {"hook", "payoff", "ending"}:
            reasons.append("supports_story_structure")
        moment["selection_reasons"] = reasons or ["maintains_source_coverage"]
        selected.append(moment)
    return selected[:limit]


def build_story_assessment(moments: list[dict[str, Any]], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize story coverage and source-backed alternatives for the editor."""

    if policy and policy.get("bloopers_requested"):
        return {
            "version": STORY_INTELLIGENCE_VERSION,
            "intent": "bloopers", "review_mode": "outtake_review",
            "coverage": {}, "gaps": [], "candidate_moments": {},
            "duplicate_idea_groups": [], "clean_spoken_edit_points": 0,
            "source_moments_considered": len(moments), "hosted_model_calls": 0,
            "recommendations": [
                "Keep enough setup to understand the recorded stumble, restart or line loss.",
                "Preserve its real reaction or recovery in source order; an unresolved question can be the ending.",
                "Keep a short earned comic beat and trim empty waiting. A restart can be the joke, not a duplicate to remove.",
                "Do not add a product benefit, sales payoff or call to action unless explicitly requested.",
            ],
        }

    candidates: dict[str, list[dict[str, Any]]] = {role: [] for role in _ROLE_ORDER}
    spoken = [moment for moment in moments if moment.get("kind") == "spoken"]
    spoken_assets = {moment.get("asset_id") for moment in spoken}
    for moment in moments:
        reason = production_chatter_reason(str(moment.get("text") or ""))
        if reason is not None and reason != "possible_script_discussion":
            continue
        if moment.get("kind") == "visual_window" and moment.get("asset_id") in spoken_assets:
            # A generic scene interval supplies no dialogue evidence for a hook
            # or a payoff when transcript-backed moments are available.
            continue
        role_scores = moment.get("role_scores") if isinstance(moment.get("role_scores"), dict) else {}
        suggested = set(moment.get("suggested_roles") or [])
        for role in _ROLE_ORDER:
            score = float(role_scores.get(role) or (0.5 if role in suggested else 0))
            if score >= 0.35:
                candidates[role].append(
                    {
                        "asset_id": moment.get("asset_id"),
                        "source_name": moment.get("source_name"),
                        "moment_id": moment.get("moment_id"),
                        "start_seconds": moment.get("start_seconds"),
                        "end_seconds": moment.get("end_seconds"),
                        "score": round(score, 3),
                        "text": str(moment.get("text") or "")[:220],
                    }
                )
    for values in candidates.values():
        values.sort(key=lambda item: (-float(item["score"]), str(item.get("asset_id") or "")))
        del values[3:]

    duplicate_groups: list[list[dict[str, Any]]] = []
    used: set[int] = set()
    for left_index, left in enumerate(spoken):
        if left_index in used:
            continue
        group = [left]
        for right_index in range(left_index + 1, len(spoken)):
            if right_index not in used and _similarity(left, spoken[right_index]) >= 0.72:
                group.append(spoken[right_index])
                used.add(right_index)
        if len(group) > 1:
            used.add(left_index)
            duplicate_groups.append(
                [
                    {
                        "asset_id": item.get("asset_id"),
                        "moment_id": item.get("moment_id"),
                        "start_seconds": item.get("start_seconds"),
                        "text": str(item.get("text") or "")[:160],
                    }
                    for item in group[:4]
                ]
            )

    required_roles = ("hook", "context", "development", "payoff", "ending")
    coverage = {role: bool(candidates[role]) for role in required_roles}
    gaps = [role for role, present in coverage.items() if not present]
    recommendations: list[str] = []
    if "hook" in gaps:
        recommendations.append("Use the clearest question, contrast, number, or reaction as the opening.")
    if "payoff" in gaps:
        recommendations.append("Preserve a complete explanatory or result-bearing phrase near the end.")
    if "ending" in gaps:
        recommendations.append("Choose a clean final thought or follow the requested closing direction.")
    if duplicate_groups:
        recommendations.append("Choose one representative from each repeated-idea group.")
    clean_cut_count = sum(
        bool((moment.get("edit_guidance") or {}).get("clean_cut_in"))
        and bool((moment.get("edit_guidance") or {}).get("clean_cut_out"))
        for moment in spoken
        if isinstance(moment.get("edit_guidance"), dict)
    )
    return {
        "version": STORY_INTELLIGENCE_VERSION,
        "coverage": coverage,
        "gaps": gaps,
        "candidate_moments": candidates,
        "duplicate_idea_groups": duplicate_groups[:6],
        "clean_spoken_edit_points": clean_cut_count,
        "recommendations": recommendations,
        "source_moments_considered": len(moments),
        "hosted_model_calls": 0,
    }
