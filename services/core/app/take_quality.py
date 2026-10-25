"""Local, source-backed take hints. These are editing evidence, not speech recognition."""

import re
from typing import Any


_WORDS = re.compile(r"[a-z0-9']+")
_PRODUCTION_CUES = (
    (r"^(?:(?:are (?:we|you))\s+)?ready(?: to (?:go|start|film))?[?.!]*$", "readiness_check"),
    (r"\b(?:let's|let us|can we) (?:try|do|record|shoot) (?:it |that |this |a )?(?:again|another|different|one more)\b", "retake_direction"),
    (r"\bnot saying (?:it|that) again\b", "retake_direction"),
    (r"^(?:(?:okay|alright|all right)[,.]? )?(?:start (?:that |it )?again|another take|take (?:two|three|four|\d+))[.!?]*$", "retake_direction"),
    (r"\b(?:cut|leave|edit) (?:that|this|it) out\b", "editing_discussion"),
    (r"\b(?:i'm|i am|we're|we are) (?:going to|gonna) get rid of (?:the|that|this)\b", "possible_script_discussion"),
)


def production_chatter_reason(text: str) -> str | None:
    normalized = " ".join(text.lower().replace("’", "'").split())
    return next((reason for pattern, reason in _PRODUCTION_CUES if re.search(pattern, normalized)), None)


def editing_policy(job: dict[str, Any]) -> dict[str, Any]:
    """A funny tone or a high effects level does not request a blooper reel."""
    instruction = " ".join(str(job.get(key) or "") for key in (
        "brief", "story_goal", "must_include", "ending_instruction",
    )).lower().replace("’", "'")
    excludes_bloopers = bool(re.search(
        r"\b(?:no|without|avoid|remove|exclude|cut|too many|don't include|do not include)\s+(?:the |any |all )?(?:bloopers?|outtakes?)\b",
        instruction,
    ))
    requests_bloopers = bool(re.search(r"\b(?:bloopers?|outtakes?|behind.the.scenes|making.of)\b", instruction))
    promotional = bool(re.search(r"\b(?:ad|ads|advert|advertisement|commercial|promo|promotional|product demo)\b",
                                 instruction + " " + str(job.get("project_name") or "").lower()))
    return {
        "story_first": True,
        "promotional": promotional,
        "bloopers_requested": requests_bloopers and not excludes_bloopers,
        "preserve_pauses_requested": bool(re.search(
            r"\b(?:keep|preserve|hold|leave)\b.{0,35}\b(?:pause|pauses|silence|reaction)\b", instruction)),
        "effects_change_story_goal": False,
    }


def take_quality_report(segments: list[dict[str, Any]]) -> dict[str, Any]:
    chatter = []
    candidates = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "").strip()
        reason = production_chatter_reason(text)
        if reason:
            chatter.append({"start": segment["start"], "end": segment["end"], "text": text[:220], "reason": reason})
        tokens = _WORDS.findall(text.lower())
        if reason or len(tokens) < 5:
            continue
        end = float(segment["end"])
        # ASR often splits one sentence across two neighbouring segments.
        # Keep the continuation visible when comparing alternative takes.
        if index + 1 < len(segments) and not text.endswith((".", "?", "!")):
            following = segments[index + 1]
            continuation = str(following.get("text") or "").strip()
            if 0 <= float(following["start"]) - end <= 0.35 and not production_chatter_reason(continuation):
                text += " " + continuation
                end = float(following["end"])
        candidates.append({"start": segment["start"], "end": end, "text": text,
                           "prefix": tokens[:5]})
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for candidate in candidates:
        groups.setdefault(tuple(candidate["prefix"]), []).append(candidate)
    repeats = []
    for group in groups.values():
        if len(group) < 2:
            continue
        public = [{key: value for key, value in item.items() if key != "prefix"} for item in group]
        preferred = max(public, key=lambda item: (len(_WORDS.findall(item["text"])), item["start"]))
        indexes = sorted({0, min(1, len(public) - 1), public.index(preferred), len(public) - 1})
        repeats.append({"candidates": [{**public[index], "text": public[index]["text"][:300]} for index in indexes],
                        "candidate_count": len(public), "compare_first_start": preferred["start"],
                        "note": "Compare the fuller take first; verify meaning and delivery against the transcript. Do not repeat every take."})
    return {"version": "1.0", "production_chatter": chatter[:24],
            "production_chatter_count": len(chatter),
            "repeated_take_groups": repeats[:6], "hosted_model_calls": 0}


def validate_story_content(plan: Any, assets: list[dict[str, Any]], policy: dict[str, Any]) -> None:
    """Reject substantial production chatter in a finished promotional story."""
    if not policy.get("promotional") or policy.get("bloopers_requested"):
        return
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    chatter_seconds = 0.0
    examples = []
    for clip in plan.clips:
        asset = inventory.get(str(clip.asset_id), {})
        for segment in asset.get("transcript_segments", []):
            reason = production_chatter_reason(str(segment.get("text") or ""))
            # This wording can be legitimate narration (e.g. a cleaning demo).
            # Use it as a soft hint only; explicit retake directions are enforceable.
            if reason is None or reason == "possible_script_discussion":
                continue
            overlap = max(0.0, min(clip.source_out, float(segment["end"]))
                          - max(clip.source_in, float(segment["start"])))
            if overlap:
                chatter_seconds += overlap
                examples.append(str(segment["text"])[:100])
    if chatter_seconds > 0.75:
        raise ValueError(
            f"selected {chatter_seconds:.2f}s of production/retake chatter ({'; '.join(examples[:3])}). "
            "Use a clean take and finish the subject's story. A funny tone or meme-heavy effects do not "
            "request outtakes; keep only a brief useful reaction unless the brief explicitly requests bloopers."
        )
