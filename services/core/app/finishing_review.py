"""Inspect saved executable treatments without judging taste or making calls."""


def treatment_timeline(context, plan):
    events, starts, durations = [], [], []
    cursor = 0.0
    for clip in plan.clips:
        starts.append(cursor)
        duration = float(getattr(clip, "duration", clip.source_out - clip.source_in))
        durations.append(duration)
        cursor += duration

    def add(kind, label, start, end, detail="", clip_index=None):
        events.append({"kind": kind, "label": str(label)[:120], "start": round(max(0, start), 3),
            "end": round(min(cursor, end), 3), "detail": str(detail)[:240], "clip_index": clip_index})

    for index, clip in enumerate(plan.clips):
        at, end = starts[index], starts[index] + durations[index]
        if index:
            labels = {"cut": "Picture cut", "cross_dissolve": "Short picture dissolve", "dip_to_black": "Dip to black"}
            add("cut" if clip.transition == "cut" else "transition", labels[clip.transition], at, at,
                "Boundary in the saved cut.", index)
        if clip.visual_preset != "standard":
            add("framing", clip.visual_preset.replace("_", " ").capitalize(), at, end, clip.editorial_intent, index)
        if clip.visual_preset == "rhythmic_punch":
            beat = at + 2.5
            while beat < end - 0.05:
                add("framing_beat", "Rhythmic framing change", beat, beat, clip_index=index)
                beat += 2.5

    inventory = {str(item["asset_id"]): item for item in context.get("creative_effect_library", [])}
    for cue in plan.effects:
        item = inventory.get(str(cue.asset_id), {})
        kind = "sound" if item.get("kind") in {"sound_effect", "meme_sound"} else "graphic"
        add(kind, item.get("title") or "Library effect", cue.start_seconds, cue.start_seconds + cue.duration_seconds, cue.purpose)
    for cue in plan.broll:
        add("broll", "Picture-only cutaway", cue.start_seconds, cue.start_seconds + cue.duration_seconds, cue.editorial_intent)

    tools = plan.finishing
    if tools:
        from app.product_tracking import crop_filter
        size = {"vertical": (540, 960), "square": (540, 540), "landscape": (960, 540)}.get(context.get("job", {}).get("output_aspect"), (540, 960))
        for profile in tools.product_profiles:
            if crop_filter(plan, profile.clip_index, *size):
                at = starts[profile.clip_index]
                add("framing", "Marked product follow", at, at + durations[profile.clip_index],
                    "Owner-selected first-frame region; local appearance matching, no semantic recognition. Review the whole shot.", profile.clip_index)
        for index in tools.stabilize_clips:
            add("framing", "Gentle camera-shake reduction", starts[index], starts[index] + durations[index],
                "Local translation-shake filter and approximately 6% edge crop; review motion and subject framing.", index)
        for profile in tools.visual_profiles:
            at = starts[profile.clip_index]
            from app.visual_finishing import source_crop_filter
            size = {"vertical": (540, 960), "square": (540, 540), "landscape": (960, 540)}.get(context.get("job", {}).get("output_aspect"), (540, 960))
            if tools.smart_framing == "face" and source_crop_filter(plan, profile.clip_index, *size):
                add("framing", "Sampled face follow", at, at + durations[profile.clip_index],
                    "Local single-face samples; no identity or product recognition. Tighter delivery crops may retain centre framing.", profile.clip_index)
            if tools.shot_match and profile.brightness and not any(c.clip_index == profile.clip_index for c in tools.colours):
                add("colour", "Small exposure match", at, at + durations[profile.clip_index], f"Brightness {profile.brightness:+.3f}; no saturation or HDR override.", profile.clip_index)
        for motion in tools.motions:
            at = starts[motion.clip_index]
            add("framing", "Anchored camera move", at, at + durations[motion.clip_index],
                f"{len(motion.points)} control points; crop anchors do not track a subject.", motion.clip_index)
        for region in tools.caption_regions:
            add("captions", "Timed caption placement", region.start, region.end, region.position.replace("_", " "))
        for cue in tools.callouts:
            add("callout", "Text: " + cue.text, cue.start, cue.end, f"{cue.style}; {cue.animation}")
        for cue in tools.visual_beats:
            detail = f"Native picture treatment; {cue.intensity} strength"
            if cue.preset == "live_cursor":
                detail += (f"; bounded frame coordinates {cue.cursor_start_x:.2f},{cue.cursor_start_y:.2f} to "
                           f"{cue.cursor_end_x:.2f},{cue.cursor_end_y:.2f}; click pulse {'on' if cue.click else 'off'}; no object tracking")
            elif cue.preset == "letter_dive":
                detail += f"; {cue.position} position; source-backed text: {cue.letter_text}"
            else:
                detail += f"; {cue.position} position"
            add("graphic", cue.preset.replace("_", " ").capitalize(), cue.start, cue.end,
                detail + "; recorded dialogue timing is unchanged and captions stay above the effect.")
        for cue in tools.pointers:
            add("graphic", "Fixed " + cue.shape, cue.start, cue.end, "Fixed coordinates; no object tracking.")
        for cue in tools.music_regions:
            add("music", "Music pause" if cue.gain_db <= -60 else "Music reduction", cue.start, cue.end, f"{cue.gain_db:+g} dB; dialogue unchanged.")
        for region in tools.audio_regions:
            add("voice", "Voice level", region.start, region.end, f"{region.gain_db:+g} dB")
        for layer in tools.layers:
            add("layer", "Picture layer", layer.start, layer.end,
                "Freeze" if layer.freeze else f"{layer.playback_rate:g}× picture speed; source audio unused.")
        for colour in tools.colours:
            add("colour", "Local colour adjustment", starts[colour.clip_index], starts[colour.clip_index] + durations[colour.clip_index], clip_index=colour.clip_index)
        for join in tools.audio_joins:
            at = starts[join.clip_index]
            add("voice", "Recorded audio lead/tail", at - join.lead_seconds, at + durations[join.clip_index] + join.tail_seconds, clip_index=join.clip_index)
        if tools.voice_denoise:
            add("voice", "Gentle voice denoising", 0, cursor)
    events.sort(key=lambda event: (event["start"], event["kind"]))
    return {"version": 1, "events": events[:240], "event_count": len(events), "duration_seconds": round(cursor, 3),
        "additional_model_calls": 0, "basis": "saved_plan_not_pixel_measurement",
        "note": "Saved treatments, not an engagement score. Cutaways and layers can cover framing; judge timing and relevance in playback."}
