"""Bounded recorded incident bundles. Text clues are not proof of comic value."""

import hashlib
import math
import re
from collections import defaultdict

from app.blooper_detection import _CLUES, QUESTION_UNCERTAINTY_PATTERN
from app.blooper_focus import _words

VERSION = 2
_END = re.compile(r"[.!?][\"'’”\])]*$|[\])]$")
_CLAUSE = re.compile(r"[,;:.!?][\"'’”\])]*$|[\])]$")
_INSTRUCTION = re.compile(r"\b(?:example|phrase|quote|say the words)\b|\b(?:if|when|whenever)\b.{0,35}\b(?:you forgot|you forget|someone|anyone|people)\b", re.I)
_RESPONSE = re.compile(r"\b(?:that's|that is) (?:hard|difficult) to (?:say|pronounce)\b|\b(?:i|we)\b.{0,20}\b(?:wrong|forgot|forget|lost|can't|cannot|couldn't|don't|do not|messed|screwed|stuffed)\b", re.I)


def _tokens(text):
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text.casefold().replace("’", "'"))


def _groups(segments):
    grouped, unusable = defaultdict(list), set()
    for segment in segments:
        if not isinstance(segment, dict) or not segment.get("asset_id"):
            continue
        identity = str(segment["asset_id"])
        try:
            start, end = float(segment["start_seconds"]), float(segment["end_seconds"])
            if not math.isfinite(start + end) or not 0 <= start < end:
                raise ValueError("unusable interval")
            words = _words(segment)
        except (KeyError, TypeError, ValueError):
            unusable.add(identity)
            continue
        grouped[identity].append((segment, words))
    for identity, items in grouped.items():
        if identity in unusable:
            continue
        current, ids, seen = [], [], set()
        for segment, words in sorted(items, key=lambda p: float(p[0]["start_seconds"])):
            if not words:
                if current:
                    yield identity, current, ids
                current, ids, seen = [], [], set()
                continue
            # Never bridge long gaps, overlapping catalogue chunks or missing
            # word data. A new group cannot borrow another recording's reaction.
            if current and (words[0]["start"] - current[-1]["end"] > .65
                            or words[0]["start"] < current[-1]["end"] - .03
                            or len(current) + len(words) > 1200):
                yield identity, current, ids
                current, ids, seen = [], [], set()
            for word in words:
                key = (word["start"], word["end"], word["text"])
                if key not in seen:
                    current.append({**word, "catalogue_id": int(segment["id"])})
                    seen.add(key)
            ids.append(int(segment["id"]))
        if current:
            yield identity, current, ids


def build_incidents(segments, avoid_ranges=()):
    """Find up to six complete local bundles per source, including later clues.

    An attempt of at least three preceding words and a recorded self-comment or
    nearby transcribed reaction are required. Laughter, waiting and repeated
    clean takes alone never qualify. ASR-only data cannot verify a visual gag.
    All selectable words/times come from existing complete word timing data.
    """
    output, counts, seen = [], defaultdict(int), set()
    for identity, words, catalogue_ids in _groups(segments):
        if counts[identity] >= 6:
            continue
        text, offsets = "", []
        for word in words:
            normalized_word = word["text"].casefold().replace("’", "'")
            offsets.append((len(text), len(text) + len(normalized_word)))
            text += normalized_word + " "
        normalized = text
        patterns = (*_CLUES, (QUESTION_UNCERTAINTY_PATTERN, "question_then_uncertainty"))
        matches = sorted(((m, reason) for pattern, reason in patterns
                          for m in re.finditer(pattern, normalized)), key=lambda p: p[0].start())
        for match, reason in matches:
            if reason == "transcribed_laughter" or counts[identity] >= 6:
                continue
            first = next((i for i, (_, end) in enumerate(offsets) if end > match.start()), None)
            last = next((i for i, (_, end) in enumerate(offsets) if end >= match.end()), None)
            if first is None or last is None:
                continue
            if reason == "question_then_uncertainty" and not any("?" in w["text"] and words[first]["start"] - w["end"] <= 2 for w in words[max(0, first - 12):first]):
                continue
            # A quoted instructional example is not a recorded mishap.
            sentence_start = max((i + 1 for i in range(first) if _END.search(words[i]["text"])), default=0)
            lead = " ".join(w["text"] for w in words[sentence_start:first])
            if _INSTRUCTION.search(lead):
                continue
            boundaries = [i for i in range(first) if words[first]["start"] - words[i]["start"] <= 6
                          and (i == 0 or _CLAUSE.search(words[i - 1]["text"]))
                          and len(_tokens(" ".join(w["text"] for w in words[i:first]))) >= 3]
            if not boundaries:
                continue
            # Use the nearest complete clause with a meaningful attempted line,
            # not an older clean introduction that merely fits the time budget.
            left = max(boundaries)
            right = last
            while right + 1 < len(words) and not _CLAUSE.search(words[right]["text"]):
                if words[right + 1]["end"] - words[last]["end"] > 2:
                    break
                right += 1
            if not _CLAUSE.search(words[right]["text"]):
                continue
            reaction_start, reaction_end = first, right
            reaction_kind = "recorded_self_comment"
            self_comment = _RESPONSE.search(" ".join(w["text"] for w in words[max(left, first - 3):right + 1]))
            if not self_comment:
                # An isolated 'oops' requires a real adjacent response, never a
                # reaction from an unrelated take or an invented laugh track.
                response = next(((m, r) for m, r in matches if m.start() >= match.end()
                    and r in {"transcribed_laughter", "self_correction", "word_stumble", "lost_line"}), None)
                if response is None:
                    continue
                m, reaction_kind = response
                a = next((i for i, (_, end) in enumerate(offsets) if end > m.start()), len(words))
                b = next((i for i, (_, end) in enumerate(offsets) if end >= m.end()), len(words))
                if a >= len(words) or b >= len(words) or words[a]["start"] - words[last]["end"] > 2:
                    continue
                reaction_start, reaction_end = a, b
                right = max(right, b)
                while right + 1 < len(words) and not _CLAUSE.search(words[right]["text"]):
                    if words[right + 1]["end"] - words[b]["end"] > 1.5:
                        break
                    right += 1
                reaction_end = right
                if not _CLAUSE.search(words[right]["text"]):
                    continue
            if words[right]["end"] - words[left]["start"] > 12:
                continue
            # Separate words inside an ASR chunk may still be far apart. Gaps
            # are not silence evidence, so decline rather than stitch a reaction.
            if any(b["start"] - a["end"] > 2 for a, b in zip(words[left:right], words[left + 1:right + 1])):
                continue
            anchor = (identity, words[first]["start"], words[right]["end"])
            if anchor in seen or any(e["asset_id"] == identity and abs(e["incident"]["start"] - words[first]["start"]) < 1
                                     and min(e["end"], words[right]["end"]) > max(e["start"], words[left]["start"]) for e in output):
                continue
            phrase = " ".join(w["text"] for w in words[left:right + 1])
            if len(phrase) > 900:
                continue
            if any(str(mark.get("asset_id")) == identity and max(float(mark["start_seconds"]),words[left]["start"]) < min(float(mark["end_seconds"]),words[right]["end"]) for mark in avoid_ranges):
                continue
            digest = hashlib.sha256(f"{identity}:{words[left]['start']}:{words[right]['end']}:{phrase}".encode()).hexdigest()
            evidence_id = -int(digest[:13], 16)
            output.append({"evidence_id": evidence_id, "asset_id": identity,
                "start": words[left]["start"], "end": words[right]["end"], "text": phrase,
                "blooper_candidate": True, "blooper_signals": [reason], "confidence": "possible",
                "blooper_scope_version": 1, "catalogue_ids": list(dict.fromkeys(w["catalogue_id"] for w in words[left:right + 1])),
                "incident_id": digest[:20], "incident": {"start": words[first]["start"], "end": words[last]["end"]},
                "setup": {"start": words[left]["start"], "end": words[first - 1]["end"],
                          "text": " ".join(w["text"] for w in words[left:first])[:200]},
                "reaction": {"start": words[reaction_start]["start"], "end": words[reaction_end]["end"],
                             "text": " ".join(w["text"] for w in words[reaction_start:reaction_end + 1])[:200], "kind": reaction_kind}})
            counts[identity] += 1
            seen.add(anchor)
    return output


def manual_incident_hints(assets, limit=12):
    """Range-only hints for an ordinary explicit blooper job's existing call."""
    queues, hashes = [], set()
    for asset in assets:
        identity = str(asset['asset_id'])
        checksum = asset.get('sha256') or identity
        if checksum in hashes or not asset.get('has_audio') or asset.get('library_role') == 'broll':
            continue
        hashes.add(checksum)
        avoid = [r for r in (asset.get('source_evidence') or {}).get('user_ranges', []) if r.get('role') == 'avoid']
        segments = [dict(id=i,asset_id=identity,start_seconds=s.get('start',0),end_seconds=s.get('end',0),
                         text=s.get('text',''),words=s.get('words') or [])
                    for i,s in enumerate(asset.get('transcript_segments') or []) if isinstance(s,dict)
                    and not any(max(float(r['start_seconds']),float(s.get('start',0))) < min(float(r['end_seconds']),float(s.get('end',0))) for r in avoid)]
        queues.append([dict(asset_id=identity,range=[b['start'],b['end']],incident=[b['incident']['start'],b['incident']['end']],
            setup=[b['setup']['start'],b['setup']['end']],response=[b['reaction']['start'],b['reaction']['end']],
            clue=b['blooper_signals'][0]) for b in build_incidents(segments,[dict(r,asset_id=identity) for r in avoid])])
    hints = []
    while any(queues) and len(hints)<limit:
        for queue in queues:
            if queue and len(hints)<limit:
                hints.append(queue.pop(0))
    return hints


def validate_incident_selection(script, incident_ids):
    """A cited bundle contains its real attempt and response in source order."""
    ids = [beat.get("incident_id") for beat in script]
    if not incident_ids or len(set(incident_ids)) != len(incident_ids) or set(ids) != set(incident_ids) or None in ids:
        raise ValueError("a blooper idea must cite its complete recorded incident bundles, not unrelated setup or reactions")
    for index, beat in enumerate(script):
        setup, anchor, reaction = (beat.get(key) or {} for key in ("setup", "incident", "reaction"))
        if not setup or not anchor or not reaction:
            raise ValueError("a recorded blooper needs its attempted line and real response")
        if not (beat["start"] <= setup["start"] < setup["end"] <= anchor["start"]
                < anchor["end"] <= beat["end"] and anchor["start"] <= reaction["start"] < reaction["end"] <= beat["end"]):
            raise ValueError("blooper bundle timing no longer preserves its setup, clue and real reaction")
        if any(beat["asset_id"] == old["asset_id"] and min(beat["end"], old["end"]) > max(beat["start"], old["start"]) + .01 for old in script[:index]):
            raise ValueError("selected blooper bundles overlap; choose one complete version of that incident")
    return {"version": VERSION, "incident_count": len(script), "recorded_setup_and_response": True,
            "semantic_judgement": "human_review_required", "hosted_retrieval_calls": 0}
