"""Bounded descriptor retrieval from the already approved library. No model call."""

import re

AUDIO_KINDS = {"sound_effect", "meme_sound"}


def family(item):
    return "audio" if item.get("kind") in AUDIO_KINDS else "visual"


def shortlist(context, *, limit=18):
    items = context.get("creative_effect_library", [])
    if context.get("job", {}).get("effect_level", "off") == "off":
        return []
    direction = context.get("job", {})
    text = " ".join(
        str(value or "")
        for value in [
            context.get("project", {}).get("brief"),
            direction.get("desired_feeling"),
            direction.get("story_goal"),
            context.get("selected_concept", {}).get("title"),
            *[
                str(m.get("text", ""))[:200]
                for a in context.get("assets", [])
                for m in a.get("transcript_segments", [])[:8]
            ],
        ]
    )[:12000].lower()
    tokens = set(re.findall(r"[a-z]{3,}", text))
    comedy = bool(
        re.search(r"\b(funny|comedy|bloopers?|playful|cheeky|joke|humou?r)\b", text)
    )
    serious = bool(
        re.search(r"\b(serious|respectful|no jokes|no comedy|no memes)\b", text)
    )

    def rank(item):
        tags = " ".join(item.get("tags") or [])
        words = set(
            re.findall(
                r"[a-z]{3,}",
                " ".join(str(item.get(k) or "") for k in ("title", "mood", "use_when"))
                + " "
                + tags,
            )
        )
        score = len(tokens & words) * 3
        if item.get("energy") == "low":
            score += 1
        if item.get("purpose") == "reaction" and comedy and not serious:
            score += 3
        return -score, str(item.get("title") or "").lower(), str(item.get("asset_id"))

    eligible = [
        item
        for item in items
        if not (
            serious
            and (
                item.get("kind") == "meme_sound"
                or set(item.get("tags") or []) & {"comedy", "punchline", "funny"}
            )
        )
    ]
    ordered = sorted(eligible, key=rank)
    # First preserve purpose/family coverage, then fill by relevance. Never
    # truncate the server inventory used for validation, crediting or rendering.
    result, seen = [], set()
    for item in ordered:
        bucket = (item.get("purpose"), family(item))
        if bucket not in seen and len(result) < limit:
            result.append(item)
            seen.add(bucket)
    ids = {item["asset_id"] for item in result}
    result.extend(item for item in ordered if item["asset_id"] not in ids)
    return result[:limit]


def collision(cue, earlier, inventory):
    """One audio + one visual can share a beat; same-family stacks cannot."""
    for old in earlier:
        distance = abs(float(cue["start_seconds"]) - float(old["start_seconds"]))
        if distance >= 0.5:
            continue
        paired = distance <= 0.05 and family(inventory[str(cue["asset_id"])]) != family(
            inventory[str(old["asset_id"])]
        )
        if not paired:
            return True
    return False


def bound_generated_treatments(context, plan):
    """Share the requested FX budget; explicit local finishing stays separate."""
    if plan.finishing is None:
        return plan
    maximum = {"off": 0, "subtle": 2, "social": 4, "meme_heavy": 8}.get(
        context.get("job", {}).get("effect_level", "off"), 0
    )
    available = max(0, maximum - len(plan.effects))
    names = ("callouts", "pointers", "music_regions", "visual_beats")
    cues = sorted(
        [
            (cue.start, name, index)
            for name in names
            for index, cue in enumerate(getattr(plan.finishing, name))
        ]
    )
    kept = {(name, index) for _, name, index in cues[:available]}
    tools = plan.finishing.model_copy(
        update={
            name: [
                cue
                for index, cue in enumerate(getattr(plan.finishing, name))
                if (name, index) in kept
            ]
            for name in names
        },
        deep=True,
    )
    if len(cues) > available:
        context["creative_treatment_review"] = {
            "removed": len(cues) - available,
            "reason": "shared_effect_budget",
            "additional_model_calls": 0,
        }
    if not any(tools.model_dump(mode="json").values()):
        tools = None
    changed = plan.model_copy(update={"finishing": tools}, deep=True)
    # The local renderer supports stacked transforms, but a new planner move
    # must be the only camera treatment on its clip. Frozen plans stay intact.
    for motion in tools.motions if tools else []:
        if motion.clip_index < len(changed.clips):
            changed.clips[motion.clip_index].visual_preset = "standard"
    return changed


def only_creative_treatments(tools):
    if tools is None:
        return False
    data = tools.model_dump(mode="json")
    names = {"callouts", "pointers", "music_regions", "visual_beats", "motions", "caption_regions"}
    return any(data.get(name) for name in names) and not any(
        value for name, value in data.items() if name not in names
    )


def remove_graphic_effects(plan):
    """Remove library cues and generated graphics, keeping local mix/layout."""
    tools = plan.finishing.model_copy(update={"callouts": [], "pointers": [], "visual_beats": []}, deep=True) if plan.finishing else None
    if tools and not any(tools.model_dump(mode="json").values()):
        tools = None
    return plan.model_copy(update={"effects": [], "finishing": tools}, deep=True)
