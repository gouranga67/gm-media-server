"""One explicit editorial priority order; no model calls or saved-plan mutation."""

from app.brief_direction import read_brief, instruction_text, _positive


VERSION = "editing_contract_v1"


def editing_contract(context):
    job = context.get("job") or {}
    brief = str((context.get("project") or {}).get("brief") or job.get("brief") or "")
    direction = read_brief({**job, "brief": brief})
    text = instruction_text({**job, "brief": brief})
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
        "priority": ["source_fidelity", "explicit_brief", "complete_audio", "story", "optional_treatment"],
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
    return (
        "Editorial priority: source fidelity and the user's explicit brief, then complete audible passages, "
        "then story continuity, then optional creative treatment. Never invent or change recorded words. "
        "Story-role labels describe the selected material; they are not a quota or an advertisement template. "
        + audio +
        "Visual pacing is separate from audio pacing. High impact suggests opportunities for picture changes, "
        "not mandatory speech cuts. Effects, zooms and transitions are optional at every duration; "
        "leave them out when they weaken a moment. There is no minimum number of treatments.\n\n"
    )


def editing_receipt(context, plan, provider):
    """Describe recorded actions, never infer that an older cut used new rules."""
    tools = plan.finishing
    profiles = tools.voice_cleanup_profiles if tools and tools.voice_cleanup == "auto" else []
    return {
        "version": 1,
        "plan_source": context.get("plan_source") or (
            "local_controls" if provider.startswith("local_") else "unrecorded"
        ),
        "planning_contract": context.get("planning_contract"),
        "local_repairs": list(dict.fromkeys(context.get("local_plan_repairs") or [])),
        "local_story_changes": (context.get("story_finishing") or {}).get("changes") or [],
        "audio_processing": {
            "balanced_sources": sum(bool(p.balance_gain_db) for p in profiles),
            "compressed_sources": sum(bool(p.compress) for p in profiles),
            "denoised_sources": sum(p.noise_reduction_db > 0 for p in profiles),
        },
        "technical_checks": "Track duration and packet timing checks do not judge story quality or humour.",
    }
