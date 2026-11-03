"""User-edited, timed caption cards. No speech, media edits or model calls."""

import hashlib
import json
import re
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SubtitleCue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    start: float = Field(ge=0, le=180)
    end: float = Field(gt=0, le=180)
    text: str = Field(max_length=600)
    position: Literal["lower_safe", "middle", "upper"] | None = None
    hidden: bool = False

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        # Plain text only: renderer escapes ASS control syntax.
        return " ".join(value.split())

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end - self.start < .0009 or (not self.hidden and not self.text):
            raise ValueError("captions need text and a positive time interval; use Hide to remove a caption")
        return self


class SubtitleEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=0)
    cues: list[SubtitleCue] = Field(max_length=400)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def document_fingerprint(context, plan):
    document = context.get("_subtitle_document")
    return fingerprint(document) if matches(document, plan, prefix=bool(context.get("_subtitle_prefix_variant"))) else None


def basis(plan):
    doc = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
    return [{k: clip.get(k) for k in ("asset_id", "source_in", "source_out", "duration", "include_source_audio", "media_kind")}
            for clip in doc["clips"]]


def duration(plan):
    return sum(float(c.get("duration") if c.get("duration") is not None else c["source_out"] - c["source_in"])
               for c in (plan if isinstance(plan, dict) else plan.model_dump(mode="json"))["clips"])


def make_document(plan, events):
    total = duration(plan)
    # Only the interval actually visible in the video is editable. Saved
    # positive sync offsets may extend the ASS beyond the end of the reel.
    visible = []
    for event in sorted(events, key=lambda e: e["start"]):
        start, end = max(0, float(event["start"])), min(total, float(event["end"]))
        if end - start >= .0009:
            visible.append({**event, "start": start, "end": end})
    return {"version": 1, "basis": basis(plan), "audio_joins": (plan.get("finishing") or {}).get("audio_joins", []),
            "timing_offset_seconds": float(plan.get("caption_timing_offset_seconds") or 0),
            "duration": total, "cues": [SubtitleCue(id=f"cue-{index:04d}", **{
                k: event[k] for k in ("start", "end", "text", "position") if k in event
            }).model_dump() for index, event in enumerate(visible)]}


def validate_cues(cues, total):
    result = [SubtitleCue.model_validate(c).model_dump() for c in cues]
    previous = 0.0
    identities = set()
    for cue in result:
        if cue["id"] in identities or cue["start"] < previous - .001 or cue["end"] > total + .025:
            raise ValueError("caption times must stay in order, inside the edit, without duplicate IDs")
        identities.add(cue["id"])
        previous = cue["start"]
    return result


def matches(document, plan, *, prefix=False):
    if not document or document.get("version") != 1:
        return False
    current, saved = basis(plan), document.get("basis")
    doc = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
    joins = (doc.get("finishing") or {}).get("audio_joins", [])
    if not prefix:
        return current == saved and joins == document.get("audio_joins", [])
    if not saved or len(current) > len(saved):
        return False
    for index, clip in enumerate(current):
        old = saved[index]
        if index < len(current) - 1:
            if clip != old:
                return False
        elif (any(clip[k] != old[k] for k in clip if k not in {"source_out", "duration"})
              or (clip.get("source_out") is not None and clip["source_out"] > old["source_out"] + .001)):
            return False
    return True


def resolve_events(context, plan, events):
    document = context.get("_subtitle_document")
    if not document:
        return events
    if not matches(document, plan, prefix=bool(context.get("_subtitle_prefix_variant"))):
        context["subtitle_notice"] = "The cut changed; timed subtitle edits were reset to match the new speech."
        return events
    document = retime_document(document, plan)
    total = duration(plan)
    result = []
    for cue in validate_cues(document["cues"], document["duration"]):
        if cue["hidden"] or cue["start"] >= total:
            continue
        end = min(cue["end"], total)
        if end - cue["start"] >= (.08 if context.get("_subtitle_prefix_variant") else .0009):
            result.append({k: v for k, v in {**cue, "end": end}.items() if k not in {"id", "hidden"} and v is not None})
    return result


def retime_document(document, plan):
    doc = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
    offset = float(doc.get("caption_timing_offset_seconds") or 0)
    delta = offset - float(document.get("timing_offset_seconds") or 0)
    result = deepcopy(document)
    if delta:
        total = result["duration"]
        for cue in result["cues"]:
            start, end = max(0, cue["start"] + delta), min(total, cue["end"] + delta)
            if end - start < .08:
                cue["hidden"] = True
                start = min(max(0, start), total - .08)
                end = start + .08
            cue.update(start=round(start, 3), end=round(end, 3))
    result["timing_offset_seconds"] = offset
    return result


def corrected_document(document, corrections):
    from app.caption_text import replace_caption_phrase
    result = deepcopy(document)
    previous = document.get("caption_corrections_snapshot") or []
    for correction in corrections:
        if correction in previous:
            continue
        for cue in result["cues"]:
            cue["text"] = replace_caption_phrase(cue["text"], correction["original_text"], correction["replacement_text"])
    result["caption_corrections_snapshot"] = corrections
    return result


def parse_ass(text):
    """Read the exact saved render's caption layer, not decorative callouts."""
    events = []
    def seconds(stamp):
        h, m, s = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    for line in text.splitlines():
        if not line.startswith("Dialogue: "):
            continue
        values = line[len("Dialogue: "):].split(",", 9)
        if len(values) != 10 or values[3] != "GMBlue" or values[0] != "0":
            continue
        caption = values[9]
        alignment = re.search(r"\{\\an([258])\\pos\(", caption)
        position = {"2": "lower_safe", "5": "middle", "8": "upper"}.get(alignment[1]) if alignment else None
        caption = re.sub(r"(?<!\\)\{\\[^}]*\}", "", caption)
        caption = re.sub(r"\\([\\{}Nn])", lambda m: " " if m[1] in "Nn" else m[1], caption)
        events.append({"start": seconds(values[1]), "end": seconds(values[2]), "text": caption,
                       **({"position": position} if position else {})})
    return events
