"""One explicit editorial priority order; no model calls or saved-plan mutation."""

import re

from app.brief_direction import read_brief, instruction_text, _positive
from app.effect_registry import EFFECT_REGISTRY_VERSION, EFFECT_DEFINITIONS


VERSION = "editing_contract_v2"


_SCRIPT_DIRECTIVE = re.compile(
    r"\b(?:use|follow|read|keep|preserve|say|speak)\b[^.;!?\n]{0,45}"
    r"\b(?:this|the|my|following|supplied|provided)\b[^.;!?\n]{0,20}\bscript\b"
    r"|\bscript\b[^.;!?\n]{0,35}\b(?:exactly|verbatim|word[ -]for[ -]word|as written)\b",
    re.IGNORECASE,
)
_SCRIPT_HEADING = re.compile(
    r"^\s*(?:voiceover\s+|spoken\s+|recorded\s+)?script\s*:\s*(?:\S.*)?$",
    re.IGNORECASE,
)
_SCENE_ITEM = re.compile(
    r"^\s*(?:scene|shot|beat)\s*(?:#\s*)?(\d{1,3})\s*(?:[.):-]|\s+-)\s*(\S.*)$",
    re.IGNORECASE,
)
_NUMBERED_ITEM = re.compile(r"^\s*(\d{1,3})[.)]\s+(\S.*)$")
_BULLET_ITEM = re.compile(r"^\s*[-*•]\s+(\S.*)$")
AI_DECISIONS = ["timing", "framing", "captions", "music", "effects", "supporting_pictures"]
_PUBLISHING_PRESETS = (
    ("instagram_reel", r"\binstagram\b"),
    ("tiktok", r"\btik[ -]?tok\b"),
    ("youtube_short", r"\byoutube\s+shorts?\b|\bshorts?\s+for\s+youtube\b"),
    ("linkedin_landscape", r"\blinked[ -]?in\b"),
    ("facebook_square", r"\bfacebook\b"),
)


def _positive_match(text, pattern):
    """Use the existing clause-aware negation rule with a compiled expression."""
    return _positive(text.lower().replace("’", "'"), pattern.pattern)


def _suggested_publishing_preset(brief):
    text = str(brief or "").lower().replace("’", "'")
    matches = [preset for preset, pattern in _PUBLISHING_PRESETS if _positive(text, pattern)]
    return matches[0] if len(matches) == 1 else "custom"


def _instruction_structure(brief):
    """Conservatively identify user-authored structure without an AI request.

    This deliberately needs visible formatting or an explicit script directive.
    Ordinary prose containing numbers or the word ``script`` remains a free brief.
    """
    lines = [line.strip() for line in str(brief or "").splitlines() if line.strip()]
    scene_items = [match.group(2) for line in lines if (match := _SCENE_ITEM.match(line))]
    numbered_items = [match.group(2) for line in lines if (match := _NUMBERED_ITEM.match(line))]
    bullet_items = [match.group(1) for line in lines if (match := _BULLET_ITEM.match(line))]
    has_script_heading = any(_SCRIPT_HEADING.match(line) for line in lines)
    has_script_directive = _positive_match(str(brief or ""), _SCRIPT_DIRECTIVE)

    if has_script_heading or has_script_directive:
        return {
            "instruction_mode": "supplied_script",
            "wording_fidelity": "verbatim",
            "sequence_locked": True,
            "required_item_count": max(1, len(scene_items), len(numbered_items), len(bullet_items)),
            "interpretation": "Follow the supplied script and its order.",
        }
    if len(scene_items) >= 2:
        return {
            "instruction_mode": "ordered_scenes",
            "wording_fidelity": "meaning",
            "sequence_locked": True,
            "required_item_count": len(scene_items),
            "interpretation": f"Follow all {len(scene_items)} supplied scenes in order.",
        }
    ordered_items = numbered_items if len(numbered_items) >= 2 else bullet_items
    if len(ordered_items) >= 2:
        return {
            "instruction_mode": "ordered_points",
            "wording_fidelity": "meaning",
            "sequence_locked": True,
            "required_item_count": len(ordered_items),
            "interpretation": f"Include all {len(ordered_items)} supplied points in order.",
        }
    return {
        "instruction_mode": "creative_brief",
        "wording_fidelity": "flexible",
        "sequence_locked": False,
        "required_item_count": 0,
        "interpretation": "Use the brief as creative direction.",
    }


def interpret_brief(brief):
    """Return the local, user-visible reading of a brief."""
    return {
        **_instruction_structure(brief),
        "ai_may_decide": list(AI_DECISIONS),
        "suggested_publishing_preset": _suggested_publishing_preset(brief),
    }


def _required_items(brief, mode):
    """Extract only visibly supplied structure; never invent missing items."""
    raw_lines = [line.strip() for line in str(brief or "").splitlines() if line.strip()]
    if mode == "ordered_scenes":
        return [match.group(2).strip() for line in raw_lines if (match := _SCENE_ITEM.match(line))]
    if mode == "ordered_points":
        numbered = [match.group(2).strip() for line in raw_lines if (match := _NUMBERED_ITEM.match(line))]
        if len(numbered) >= 2:
            return numbered
        return [match.group(1).strip() for line in raw_lines if (match := _BULLET_ITEM.match(line))]
    if mode != "supplied_script":
        return []

    for index, line in enumerate(raw_lines):
        heading = _SCRIPT_HEADING.match(line)
        directive = _SCRIPT_DIRECTIVE.search(line)
        if not heading and not directive:
            continue
        inline = line.split(":", 1)[1].strip() if ":" in line else ""
        items = ([inline] if inline else []) + raw_lines[index + 1 :]
        return [item for item in items if item]
    return []


def brief_contract(brief):
    """Return the internal contract, including text needed for local validation."""
    public = interpret_brief(brief)
    return {**public, "required_items": _required_items(brief, public["instruction_mode"])}


def editing_contract(context):
    job = context.get("job") or {}
    brief = str((context.get("project") or {}).get("brief") or job.get("brief") or "")
    direction = read_brief({**job, "brief": brief})
    text = instruction_text({**job, "brief": brief})
    structure = interpret_brief(brief)
    purpose = (job.get("editorial_policy") or {}).get("intent") or direction["purpose"]
    # Audio pacing is independent of the visual style. Ordinary stories keep
    # complete exchanges; explicitly promotional/tight edits can trim pauses.
    connected = direction["preserve_speech"] or _positive(text,
        r"\b(?:keep|preserve|retain)\b[^.;!?]{0,45}\b(?:conversations?|ambien[ct]e?|natural sound|exchanges?)\b",
    )
    tight = _positive(text, r"\b(?:tighten|trim|remove|shorten)\b[^.;!?]{0,35}\b(?:pauses?|silences?|dead air|waiting)\b")
    if direction["visual_led"] and not connected:
        audio = "music_led"
    elif (purpose == "promotion" or tight) and not connected:
        audio = "tight_dialogue"
    else:
        audio = "connected_passages"
    return {
        "version": VERSION,
        "purpose": purpose,
        "audio_pacing": audio,
        "visual_style": job.get("edit_style") or "clean",
        "creative_quotas": False,
        "preserve_natural_audio": connected,
        **structure,
        "priority": [
            "rights_privacy_safety",
            "source_fidelity",
            "explicit_exclusions",
            "supplied_script_or_order",
            "explicit_brief",
            "complete_audio",
            "story",
            "optional_treatment",
        ],
    }


def contract_instructions(context):
    contract = editing_contract(context)
    audio = {
        "connected_passages": (
            "Keep complete conversational exchanges and useful natural sound together. Avoid a sequence "
            "of disconnected short remarks. Preserve the atmosphere and necessary lead-in/reaction; "
            "remove only clearly disposable waiting. A change in picture need not change the audio. "
        ),
        "tight_dialogue": (
            "Choose clean complete explanations. Tighten disposable pauses and repeated takes while "
            "preserving connecting words, breath handles and the full ending. "
        ),
        "music_led": (
            "Let the requested music support the visual sequence. Include source speech only as complete, "
            "understandable passages; avoid rapid on/off fragments of conversation. "
        ),
    }[contract["audio_pacing"]]
    structure = {
        "supplied_script": (
            "The brief contains a supplied script. Treat its wording and sequence as authoritative. Match it to "
            "recorded source speech without paraphrasing, reordering or silently dropping lines. If the recorded "
            "sources or hard duration limit cannot support the complete script, explain the conflict in "
            "editorial_summary instead of inventing words or pretending the script was followed. "
        ),
        "ordered_scenes": (
            "The brief contains an ordered scene plan. Include every supplied scene in that order. You may choose "
            "source-backed timing, framing and treatment inside each scene, but do not merge, omit or reorder scenes "
            "without an explicit later instruction. "
        ),
        "ordered_points": (
            "The brief contains ordered points. Include every supplied point in that order, preserving its meaning "
            "and complete recorded explanation. Do not silently omit or reorder a point to reach a preferred length. "
        ),
        "creative_brief": "Use the brief as creative direction while preserving every explicit requirement. ",
    }[contract["instruction_mode"]]
    return (
        "Editorial priority: rights, privacy and safety; recorded source truth; explicit exclusions; supplied "
        "script or requested order; then the rest of the user's brief, complete audible passages, story continuity "
        "and optional creative treatment. "
        + structure
        + "Never invent or change recorded words. "
        "Story-role labels describe the selected material; they are not a quota or an advertisement template. "
        + audio +
        "Visual pacing is separate from audio pacing. High impact suggests opportunities for picture changes, "
        "not mandatory speech cuts. Effects, zooms and transitions are optional at every duration; "
        "leave them out when they weaken a moment. There is no minimum number of treatments.\n\n"
    )


def _clip_duration(plan, clip):
    return float(clip.duration) if hasattr(clip, "duration") else float(clip.source_out - clip.source_in)


def _structural_effect_skip(plan, preset):
    """Return a proven exclusion only; subjective suitability stays owner-reviewed."""
    if preset == "paper_tear":
        eligible = any(
            index > 0 and clip.transition == "cut" and _clip_duration(plan, clip) >= 0.4
            for index, clip in enumerate(plan.clips)
        )
        if not eligible:
            return "ineligible", "No eligible ordinary cut with at least 0.4 seconds in the incoming clip remained in the saved plan."
    if preset == "dolly_zoom":
        tools = plan.finishing
        motion_clips = {item.clip_index for item in tools.motions} if tools else set()
        tracked_clips = {
            item.clip_index
            for name in ("visual_profiles", "product_profiles")
            for item in (getattr(tools, name, []) if tools else [])
        }
        timeline = 0.0
        eligible = False
        for index, clip in enumerate(plan.clips):
            duration = _clip_duration(plan, clip)
            end = timeline + duration
            is_video = getattr(clip, "media_kind", "video") == "video"
            layer_conflict = bool(tools and any(layer.start < end and layer.end > timeline for layer in tools.layers))
            if (is_video and 1 <= duration <= 8 and clip.visual_preset == "standard"
                    and index not in motion_clips and index not in tracked_clips and not layer_conflict):
                eligible = True
                break
            timeline = end
        if not eligible:
            return "ineligible", "No complete 1–8 second video clip remained without another camera treatment or overlapping picture layer."
    return "owner_review", "The planner returned no instance of this optional effect; visual suitability still needs owner playback judgement."


def _effect_decision_receipt(context, plan):
    tools = plan.finishing
    chosen = {}
    for cue in tools.visual_beats if tools else []:
        chosen.setdefault(cue.preset, []).append(cue)
    review = context.get("creative_treatment_review") or {}
    rejected = set(review.get("rejected_visual_beats") or [])
    source = context.get("plan_source") or "unrecorded"
    effect_level = (context.get("job") or {}).get("effect_level", "off")
    items = []
    for definition in EFFECT_DEFINITIONS:
        cues = chosen.get(definition.preset, [])
        if cues:
            reason = {
                "model_plan": "Selected in the AI plan and retained after GM Server validated its schema, duration and conflicts.",
                "saved_plan": "Present in the saved plan; no new AI effect decision was made for this render.",
                "local_controls": "Added or retained by local editing controls; no AI effect selection was made.",
            }.get(source, "Present in the final saved plan; the original selection route was not recorded.")
            items.append({
                "preset": definition.preset,
                "label": definition.label,
                "decision": "selected",
                "eligibility": "eligible",
                "reason": reason,
                "evidence": [f"{cue.start:.2f}–{cue.end:.2f}s · {cue.intensity} strength" for cue in cues],
            })
        elif definition.preset in rejected:
            items.append({
                "preset": definition.preset,
                "label": definition.label,
                "decision": "rejected",
                "eligibility": "eligible",
                "reason": "The AI plan proposed this effect, but GM Server removed it because the shared effect budget was already full.",
                "evidence": ["Local shared-effect budget check"],
            })
        elif effect_level == "off":
            items.append({
                "preset": definition.preset,
                "label": definition.label,
                "decision": "skipped",
                "eligibility": "disabled",
                "reason": "Decorative effects were disabled for this job.",
                "evidence": [],
            })
        else:
            eligibility, reason = _structural_effect_skip(plan, definition.preset)
            if source == "saved_plan" and eligibility == "owner_review":
                reason = "The saved plan contains no instance of this effect; no new AI decision was made."
            elif source == "local_controls" and eligibility == "owner_review":
                reason = "This local change did not add the effect; no AI decision was made."
            items.append({
                "preset": definition.preset,
                "label": definition.label,
                "decision": "skipped",
                "eligibility": eligibility,
                "reason": reason,
                "evidence": [],
            })
    counts = {decision: sum(item["decision"] == decision for item in items)
              for decision in ("selected", "rejected", "skipped")}
    return {
        "version": 1,
        "registry_version": EFFECT_REGISTRY_VERSION,
        "counts": counts,
        "items": items,
        "note": "This records the returned plan and local validation rules, not hidden model reasoning or a quality score.",
    }


def editing_receipt(context, plan, provider):
    """Describe recorded actions, never infer that an older cut used new rules."""
    tools = plan.finishing
    profiles = tools.voice_cleanup_profiles if tools and tools.voice_cleanup == "auto" else []
    return {
        "version": 2,
        "plan_source": context.get("plan_source") or (
            "local_controls" if provider.startswith("local_") else "unrecorded"
        ),
        "planning_contract": context.get("planning_contract"),
        "brief_contract_review": context.get("brief_contract_review"),
        "local_repairs": list(dict.fromkeys(context.get("local_plan_repairs") or [])),
        "local_story_changes": (context.get("story_finishing") or {}).get("changes") or [],
        "audio_processing": {
            "balanced_sources": sum(bool(p.balance_gain_db) for p in profiles),
            "compressed_sources": sum(bool(p.compress) for p in profiles),
            "denoised_sources": sum(p.noise_reduction_db > 0 for p in profiles),
        },
        "technical_checks": "Track duration and packet timing checks do not judge story quality or humour.",
        "effect_decisions": _effect_decision_receipt(context, plan),
    }
