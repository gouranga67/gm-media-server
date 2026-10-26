"""Conservative local reading of explicit editorial directions, not an LLM."""

import re
from typing import Any


def instruction_text(job: dict[str, Any]) -> str:
    return (
        " ".join(
            str(job.get(key) or "")
            for key in (
                "brief",
                "story_goal",
                "desired_feeling",
                "must_include",
                "ending_instruction",
            )
        )
        .lower()
        .replace("’", "'")
    )


def _positive(text: str, pattern: str) -> bool:
    for match in re.finditer(pattern, text):
        prefix = text[max(0, match.start() - 65) : match.start()]
        # Only inspect the current short clause; a previous exclusion must not
        # negate a later request ("no fast cuts; make it gentle").
        clause = re.split(r"[.;!?\n]|\bbut\b|\binstead\b", prefix)[-1]
        if not re.search(
            r"\b(?:no|not|never|without|avoid|remove|exclude|omit|cut|too many|don't|do not)\b(?:\W+\w+){0,5}\W*$",
            clause,
        ):
            return True
    return False


def read_brief(job: dict[str, Any]) -> dict[str, Any]:
    text = instruction_text(job)
    bloopers = _positive(text, r"\b(?:bloopers?|outtakes?)\b")
    no_ad = any(
        re.search(
            r"\b(?:not|no|without|avoid|don't|do not)\b(?:\W+\w+){0,5}\W+\b(?:ad|ads|advert|advertisement|commercial|promotional)\b",
            clause,
        )
        for clause in re.split(r"[.;!?\n]|\bbut\b|\binstead\b", text)
    )
    promotion = not no_ad and _positive(
        text, r"\b(?:ad|ads|advert|advertisement|commercial|promotional|product demo)\b"
    )
    purpose = "bloopers" if bloopers else "promotion" if promotion else "story"
    speech = _positive(
        text,
        r"\b(?:keep|preserve|retain|continue)\b[^.;!?]{0,65}\b(?:explanation|dialogue|speech|narration|voice|whole sentence)\b|\b(?:speech|dialogue|voice)[ -]led\b|\bvoice[ -]?over\b",
    )
    visual = (
        _positive(
            text,
            r"\b(?:music|visual|picture)[ -]led\b|\bslideshow\b|\b(?:photo|silent|cinematic|feel.good) montage\b|\b(?:make|create|build|edit)\b[^.;!?]{0,35}\bmontage\b",
        )
        or text.strip() == "montage"
    )
    style = None
    if _positive(text, r"\b(?:slow|calm|gentle|relaxed|unhurried|feel.good|warm)\b"):
        style = "calm"
    elif _positive(text, r"\bhigh[ -]impact\b|\bfast[ -]paced\b"):
        style = "high_impact"
    elif _positive(text, r"\b(?:energetic|upbeat|punchy)\b"):
        style = "energetic"
    elif _positive(text, r"\b(?:minimal|clean edit|steady framing)\b"):
        style = "clean"
    return {
        "purpose": purpose,
        "explicit_purpose": bloopers or promotion or no_ad,
        "excludes_promotion": no_ad,
        "preserve_speech": speech,
        "visual_led": visual,
        "style": style,
    }
