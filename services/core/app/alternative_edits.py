"""Bounded creative history and local difference checks; no model or media calls."""

import json
import re
from difflib import SequenceMatcher


def alternative_instruction(kind: str, direction: str = "") -> str:
    task = (
        "Make a different cut of this story. Keep its central message, product facts and complete explanation. "
        "Explore another supported opening, alternate takes, pacing, relevant B-roll and framing. "
        "Make a meaningful editorial alternative, not tiny timing changes or only different music."
        if kind == "different_cut"
        else "Find a different supported story in the attached footage. Explore another angle, opening, "
        "recorded speech selection and payoff. The earlier selected concept is a reference, not a script lock. "
        "Keep the original subject, factual boundaries and requested reel purpose."
    )
    return task + (" Additional direction: " + direction if direction else "")


def _inventory(assets):
    return {str(asset["asset_id"]): asset for asset in assets}


def _identity(identity, assets):
    asset = assets.get(str(identity), {})
    # Re-uploading identical bytes cannot manufacture new footage.
    return str(asset.get("sha256") or identity)


def _ranges(document, assets):
    ranges = {}
    for clip in document.get("clips", []):
        start, end = (
            float(clip.get("source_in") or 0),
            float(clip.get("source_out") or 0),
        )
        if end <= start:
            # A still has no source time; record its presence, not an invented range.
            if float(clip.get("duration") or 0) <= 0:
                continue
            start, end = 0.0, 1.0
        key = _identity(clip["asset_id"], assets)
        ranges.setdefault(key, []).append((start, end))
    merged = {}
    for key, spans in ranges.items():
        output = []
        for start, end in sorted(spans):
            if output and start <= output[-1][1]:
                output[-1] = (output[-1][0], max(end, output[-1][1]))
            else:
                output.append((start, end))
        merged[key] = output
    return merged


def _overlap(before, after, assets):
    left, right = _ranges(before, assets), _ranges(after, assets)
    total = sum(b - a for spans in [*left.values(), *right.values()] for a, b in spans)
    shared = sum(
        max(0.0, min(b, d) - max(a, c))
        for key, spans in left.items()
        for a, b in spans
        for c, d in right.get(key, [])
    )
    return 2 * shared / total if total else 1.0


def _spoken_text(document, assets, *, limit=2400):
    parts = []
    for clip in document.get("clips", []):
        if clip.get("include_source_audio", True) is False:
            continue
        start, end = (
            float(clip.get("source_in") or 0),
            float(clip.get("source_out") or 0),
        )
        for segment in assets.get(str(clip["asset_id"]), {}).get(
            "transcript_segments", []
        ):
            words = segment.get("words") or []
            if words:
                parts.extend(
                    str(word.get("text", word.get("word", "")))
                    for word in words
                    if start <= (float(word["start"]) + float(word["end"])) / 2 < end
                )
            else:
                a, b = float(segment.get("start") or 0), float(segment.get("end") or 0)
                if min(end, b) - max(start, a) >= max(0.1, (b - a) * 0.5):
                    parts.append(str(segment.get("text") or ""))
    return " ".join(" ".join(parts).split())[:limit]


def compact_history(rows, assets):
    """Up to eight versions, under 6,000 characters of reusable selection hints."""
    inventory = _inventory(assets)
    result, remaining = [], 5600
    for row in rows[:8]:
        document = row["document"]
        clips = document.get("clips", [])
        script = _spoken_text(document, inventory, limit=280)
        summary = {
            "version": row["version"],
            "selected_speech": script,
            "opening": [
                [str(c["asset_id"]), c.get("source_in", 0), c.get("source_out", 0)]
                for c in clips[:2]
            ],
            "ending": [
                [str(c["asset_id"]), c.get("source_in", 0), c.get("source_out", 0)]
                for c in clips[-1:]
            ],
            "selection_sample": [
                [str(c["asset_id"]), c.get("source_in", 0), c.get("source_out", 0)]
                for c in clips[2 :: max(1, len(clips) // 3)][:3]
            ],
        }
        size = len(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        if size > remaining:
            break
        remaining -= size
        result.append(summary)
    return result


def prepare_alternative(context, run, rows):
    """Modify only this task's context. Original plans and source analysis stay intact."""
    kind = run.get("alternative_kind")
    if not kind:
        return
    context["alternative"] = {
        "kind": kind,
        "based_on_version": rows[0]["version"],
        "earlier_edits": compact_history(rows, context["assets"]),
        "coverage": "Reference version plus up to seven recent completed versions of this job; other jobs are not compared.",
    }
    context["_alternative_history"] = rows[:8]
    # A selected concept and its script are binding for normal cuts, but a new
    # story explicitly authorizes exploring beyond them in the attached sources.
    if kind == "different_story":
        context.pop("selected_concept", None)
        context["job"].pop("_selected_story_contract", None)


def _visual_profile(document):
    profile = []
    for clip in document.get("clips", []):
        duration = float(
            clip.get("duration")
            or (float(clip.get("source_out") or 0) - float(clip.get("source_in") or 0))
        )
        profile.extend(
            [clip.get("visual_preset", "standard")] * max(1, round(duration * 2))
        )
    return profile[:240]


def _treatment_changed(before, after):
    left, right = _visual_profile(before), _visual_profile(after)
    count = min(len(left), len(right))
    if count and sum(a != b for a, b in zip(left, right)) / count >= 0.25:
        return True

    # A two-second new cutaway is visible; a music change or a tiny cue shift
    # alone is not a meaningfully different cut.
    def cues(document):
        return {
            (
                str(c["asset_id"]),
                round(float(c.get("start_seconds") or 0)),
                round(float(c.get("duration") or c.get("duration_seconds") or 0)),
            )
            for c in document.get("broll", [])
        }

    return any(c[2] >= 2 for c in cues(before) ^ cues(after))


def _sequence_reordered(before, after, assets):
    """Recognize reordering while ignoring simple splits of the same span."""
    matched = []
    for clip in after.get("clips", []):
        start, end = (
            float(clip.get("source_in") or 0),
            float(clip.get("source_out") or 0),
        )
        if end - start < 1:
            continue
        candidates = [
            (
                max(
                    0,
                    min(end, float(old.get("source_out") or 0))
                    - max(start, float(old.get("source_in") or 0)),
                ),
                index,
            )
            for index, old in enumerate(before.get("clips", []))
            if _identity(old["asset_id"], assets) == _identity(clip["asset_id"], assets)
        ]
        overlap, index = max(candidates, default=(0, -1))
        if overlap >= 0.5:
            matched.append(index)
    return any(a > b for a, b in zip(matched, matched[1:]))


def assess_alternative(kind, document, rows, assets):
    inventory = _inventory(assets)
    spoken = re.findall(r"\w+", _spoken_text(document, inventory).casefold())
    results = []
    for row in rows[:8]:
        previous = row["document"]
        prior_words = re.findall(r"\w+", _spoken_text(previous, inventory).casefold())
        overlap = _overlap(previous, document, inventory)
        speech_similarity = (
            SequenceMatcher(None, prior_words, spoken, autojunk=False).ratio()
            if prior_words and spoken
            else None
        )
        before, after = previous.get("clips", []), document.get("clips", [])
        opening_changed = bool(
            before
            and after
            and (
                _identity(before[0]["asset_id"], inventory)
                != _identity(after[0]["asset_id"], inventory)
                or abs(
                    float(before[0].get("source_in") or 0)
                    - float(after[0].get("source_in") or 0)
                )
                >= 1
            )
        )
        similar = (
            overlap >= 0.85
            or (speech_similarity is not None and speech_similarity >= 0.8)
            if kind == "different_story"
            else overlap >= 0.85
            and not opening_changed
            and not _treatment_changed(previous, document)
            and not _sequence_reordered(previous, document, inventory)
        )
        results.append(
            {
                "version": row["version"],
                "source_overlap": round(overlap, 3),
                "speech_similarity": round(speech_similarity, 3)
                if speech_similarity is not None
                else None,
                "similar": similar,
            }
        )
    nearest = max(
        results,
        key=lambda item: (item["similar"], item["source_overlap"]),
        default=None,
    )
    similar = bool(nearest and nearest["similar"])
    return {
        "kind": kind,
        "status": "similar"
        if similar
        else "different_selections"
        if kind == "different_story"
        else "different_cut",
        "compared_versions": [item["version"] for item in results],
        "closest_version": nearest["version"] if nearest else None,
        "comparisons": results,
        "notice": (
            f"This result is still close to version {nearest['version']}. "
            "The available footage or brief may limit alternatives. Your original is retained; no automatic novelty retry was made."
            if similar
            else "The recorded selections differ from the compared versions. Watch to judge whether this tells a worthwhile different story."
            if kind == "different_story"
            else "The cut or visual treatment differs from the compared versions. Review the message and pacing before choosing."
        ),
        "semantic_judgement": "human_review_required",
        "hosted_model_calls": 0,
    }
