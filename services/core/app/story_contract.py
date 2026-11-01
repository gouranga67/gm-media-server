"""Check selected recorded story coverage/order, without claiming story judgement."""

import math
import re

_DISPOSABLE = {"um", "uh", "erm", "hmm", "okay", "alright"}


def _token(value: str) -> str:
    return re.sub(r"[^a-z0-9']", "", value.lower().replace("’", "'"))


def contract_for(angle: str, script: list[dict]) -> dict:
    return {
        "version": 1,
        "central_point": angle[:500],
        "opening_evidence_id": script[0]["evidence_id"],
        "ending_evidence_id": script[-1]["evidence_id"],
        "policy": "preserve_recorded_beats_and_order; allow_filler_and_silence_cleanup",
    }


def selected_story_contract(context: dict) -> dict | None:
    selected = context.get("selected_concept") or {}
    contract = selected.get("story_contract") or {}
    if not selected.get("script"):
        return None
    if selected.get("reel_kind") == "bloopers":
        # Only modern, word-focused incidents have a sufficiently narrow
        # selected script. Keep the user's chosen setup and reaction as well as
        # the mistake; never impose an advertising story shape on an outtake.
        if not all(beat.get("blooper_scope_version") == 1 for beat in selected["script"]):
            return None
        contract = contract_for(str(selected.get("angle") or selected.get("title") or "Selected recorded outtake"), selected["script"])
        contract["policy"] = "preserve_selected_setup_incident_reaction_and_order; allow_silence_cleanup"
    elif contract.get("version") != 1:
        return None
    return {**contract, "beats": selected["script"]}


def check_story_contract(
    plan, contract: dict | None, assets: list[dict], *, enforce: bool = True
) -> dict:
    if not contract:
        return {
            "status": "not_applicable",
            "semantic_judgement": "human_review_required",
        }
    inventory = {str(a["asset_id"]): a for a in assets}
    selections = []
    timeline = 0.0
    for clip in plan.clips:
        selections.append(
            (
                str(clip.asset_id),
                float(clip.source_in),
                float(clip.source_out),
                timeline,
            )
        )
        timeline += float(getattr(clip, "duration", clip.source_out - clip.source_in))
    checks, problems, last_position = [], [], -1.0
    beats = contract["beats"]
    # Unlike picture-only B-roll, extra spoken lines can silently change the
    # chosen concept's claim or ending. A filler-only opening is locally removable.
    for index, (identity, left, right, _) in enumerate(selections):
        selected_words = []
        for segment in inventory.get(identity, {}).get("transcript_segments", []):
            for word in segment.get("words", []):
                try:
                    a, b = float(word["start"]), float(word["end"])
                except (ValueError, TypeError, KeyError):
                    continue
                if math.isfinite(a + b) and a < b and left <= (a + b) / 2 < right:
                    selected_words.append(
                        (
                            str(word.get("text", word.get("word", ""))).strip(),
                            (a + b) / 2,
                        )
                    )
        filler = index == 0 and re.fullmatch(
            r"(?:all right|alright|okay|ok|um|uh)[,.!? ]*",
            " ".join(w for w, _ in selected_words),
            re.I,
        )
        outside = [
            word
            for word, at in selected_words
            if _token(word)
            and _token(word) not in _DISPOSABLE
            and not any(
                str(beat["asset_id"]) == identity
                and float(beat["start"]) - 0.05 <= at <= float(beat["end"]) + 0.05
                for beat in beats
            )
        ]
        if outside and not filler:
            problems.append(
                f"clip {index + 1} adds speech outside the selected story: {' '.join(outside[:6])}"
            )
    for beat in beats:
        identity = str(beat["asset_id"])
        left, right = float(beat["start"]), float(beat["end"])
        chosen = [
            s
            for s in selections
            if s[0] == identity and min(s[2], right) > max(s[1], left)
        ]
        positions = [s[3] + max(left, s[1]) - s[1] for s in chosen]
        words, critical = [], []
        for segment in inventory.get(identity, {}).get("transcript_segments", []):
            for word in segment.get("words", []):
                try:
                    a, b = float(word["start"]), float(word["end"])
                except (ValueError, TypeError, KeyError):
                    continue
                token = _token(str(word.get("text", word.get("word", ""))))
                if (
                    math.isfinite(a + b)
                    and a < b
                    and left <= (a + b) / 2 < right
                    and token
                    and token not in _DISPOSABLE
                ):
                    words.append((a + b) / 2)
                    if (
                        token
                        in {
                            "not",
                            "no",
                            "never",
                            "without",
                            "if",
                            "because",
                            "but",
                            "only",
                            "instead",
                            "cannot",
                        }
                        or token.endswith("n't")
                        or any(char.isdigit() for char in token)
                    ):
                        critical.append((a + b) / 2)
        coverage = (
            sum(any(s[1] <= w < s[2] for s in chosen) for w in words) / len(words)
            if words
            else None
        )
        protected = critical + words[:1] + words[-1:]
        if words:
            positions = [
                s[3] + word - s[1]
                for word in words
                for s in chosen
                if s[1] <= word < s[2]
            ]
        else:
            positions += [s[3] + min(right, s[2]) - s[1] for s in chosen]
        time_coverage = sum(min(s[2], right) - max(s[1], left) for s in chosen) / max(
            0.001, right - left
        )
        present = (
            bool(chosen)
            and (time_coverage >= 0.6 if coverage is None else coverage >= 0.85)
            and all(any(s[1] <= w < s[2] for s in chosen) for w in protected)
        )
        in_order = bool(positions) and min(positions) >= last_position - 0.05
        if positions:
            last_position = max(last_position, max(positions))
        checks.append(
            {
                "evidence_id": beat["evidence_id"],
                "role": beat["role"],
                "present": present,
                "in_order": in_order,
                "word_coverage": round(coverage, 3) if coverage is not None else None,
            }
        )
        if not present or not in_order:
            problems.append(
                f"selected {beat['role']} evidence {beat['evidence_id']} is missing, substantially cut or out of order"
            )
    if problems and enforce:
        raise ValueError(
            "selected story contract: "
            + "; ".join(problems[:3])
            + ". Preserve the selected recorded story; cleanup may remove fillers and silence, not its explanation or ending."
        )
    return {
        "version": 1,
        "status": "attention" if problems else "checked",
        "central_point": contract["central_point"],
        "checks": checks,
        "findings": problems,
        "semantic_judgement": "human_review_required",
        "hosted_model_calls": 0,
    }
