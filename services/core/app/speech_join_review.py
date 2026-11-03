"""Bounded measurements around real rendered speech joins; advisory only."""

import array
import math
import subprocess


def join_windows(context, plan):
    inventory = {str(a["asset_id"]): a for a in context.get("assets", [])}
    clips = list(plan.clips)
    elapsed = 0.0
    results = []
    for index, clip in enumerate(clips):
        duration = float(clip.duration if hasattr(clip, "duration") else clip.source_out - clip.source_in)
        elapsed += duration
        if index == len(clips) - 1:
            break
        following = clips[index + 1]
        if any(hasattr(c, "include_source_audio") and not c.include_source_audio for c in (clip, following)):
            continue
        gaps = []
        for current, edge in ((clip, "end"), (following, "start")):
            asset = inventory.get(str(current.asset_id), {})
            words = [w for s in asset.get("transcript_segments", []) if isinstance(s, dict)
                     for w in s.get("words") or [] if isinstance(w, dict)
                     and isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))
                     and w["end"] > current.source_in and w["start"] < current.source_out]
            gaps.append((current.source_out - max(w["end"] for w in words) if edge == "end"
                         else min(w["start"] for w in words) - current.source_in) if words else None)
        if any(g is not None for g in gaps):
            results.append({"clip_index": index, "at": round(elapsed, 3),
                            "out_clearance": gaps[0], "in_clearance": gaps[1]})
    # Inspect coverage across the reel, rather than only its opening cuts.
    if len(results) > 12:
        results = [results[round(i * (len(results) - 1) / 11)] for i in range(12)]
    return results


def inspect_joins(context, plan, path, *, timeout=4):
    joins = join_windows(context, plan)
    if not joins:
        return {"status": "not_applicable", "joins": [], "hosted_model_calls": 0}
    duration = sum(float(c.duration if hasattr(c, "duration") else c.source_out - c.source_in) for c in plan.clips)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-threads", "1",
        "-i", str(path), "-map", "0:a:0", "-t", f"{min(duration, 181):.3f}",
        "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
        capture_output=True, check=True, timeout=timeout).stdout
    samples = array.array("f", raw)

    def energy(start, end):
        values = samples[max(0, round(start * 8000)):round(end * 8000)]
        return math.sqrt(sum(v * v for v in values) / max(1, len(values)))

    for join in joins:
        at = join["at"]
        left, right = energy(at - 0.04, at), energy(at, at + 0.04)
        neighbourhood = energy(at - 0.2, at + 0.2)
        near_word = any(g is not None and g < 0.06 for g in (join["out_clearance"], join["in_clearance"]))
        audible = max(left, right) > max(0.003, neighbourhood * 0.5)
        join["review"] = bool(near_word and audible)
        join["edge_rms"] = round(max(left, right), 5)
    return {"status": "attention" if any(j["review"] for j in joins) else "measured",
            "joins": joins, "hosted_model_calls": 0,
            "note": "Source word clearance plus rendered audio energy; music or effects can mask a cut. This is not proof of a clipped phoneme."}
