"""Small native picture treatments. One picture clock, original audio untouched."""

import re
from typing import Literal
from pydantic import Field, field_validator, model_serializer, model_validator
from app.creative_treatments import TreatmentWindow
from app.effect_registry import effect_definition


class VisualBeat(TreatmentWindow):
    preset: Literal["impact_frame", "clone_row", "live_cursor", "letter_dive", "comment_drop", "voice_note", "post_wall"]
    intensity: Literal["subtle", "standard", "strong"] = "standard"
    position: Literal["upper", "center", "lower"] = "center"
    cursor_start_x: float | None = Field(default=None, ge=.08, le=.92)
    cursor_start_y: float | None = Field(default=None, ge=.1, le=.82)
    cursor_end_x: float | None = Field(default=None, ge=.08, le=.92)
    cursor_end_y: float | None = Field(default=None, ge=.1, le=.82)
    click: bool | None = None
    letter_text: str | None = Field(default=None, min_length=1, max_length=18)
    comment_text: str | None = Field(default=None, min_length=1, max_length=48)
    post_texts: list[str] | None = Field(default=None, min_length=2, max_length=3)

    @field_validator("letter_text", "comment_text")
    @classmethod
    def safe_letter_text(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value or any(character in value for character in "{}\\") or any(ord(character) < 32 for character in value):
            raise ValueError("native text effects require short plain text without subtitle commands")
        return value

    @field_validator("post_texts")
    @classmethod
    def safe_post_texts(cls, value):
        if value is None:
            return value
        cleaned = []
        for text in value:
            text = text.strip()
            if not text or len(text) > 42 or any(character in text for character in "{}\\") or any(ord(character) < 32 for character in text):
                raise ValueError("post_wall requires two or three short plain source-backed cards")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def short_beat(self):
        definition = effect_definition(self.preset)
        duration = self.end - self.start
        if not definition.minimum_duration_seconds - .0001 <= duration <= definition.maximum_duration_seconds + .0001:
            raise ValueError(
                f"{self.preset} must last {definition.minimum_duration_seconds:g}–"
                f"{definition.maximum_duration_seconds:g} seconds"
            )
        position = definition.parameter("position")
        if position is None and self.position != "center":
            raise ValueError(f"{self.preset} has a fixed frame position")
        if position is not None and self.position not in position.values:
            raise ValueError(f"{self.preset} does not support position {self.position}")
        cursor_values = (self.cursor_start_x, self.cursor_start_y, self.cursor_end_x, self.cursor_end_y, self.click)
        if self.preset == "live_cursor" and any(value is None for value in cursor_values):
            raise ValueError("live_cursor requires a bounded start, end and click choice")
        if self.preset != "live_cursor" and any(value is not None for value in cursor_values):
            raise ValueError(f"{self.preset} does not accept cursor parameters")
        if self.preset == "letter_dive" and self.letter_text is None:
            raise ValueError("letter_dive requires source-backed text")
        if self.preset != "letter_dive" and self.letter_text is not None:
            raise ValueError(f"{self.preset} does not accept letter text")
        if self.preset == "comment_drop" and self.comment_text is None:
            raise ValueError("comment_drop requires source-backed text")
        if self.preset != "comment_drop" and self.comment_text is not None:
            raise ValueError(f"{self.preset} does not accept comment text")
        if self.preset == "post_wall" and self.post_texts is None:
            raise ValueError("post_wall requires two or three source-backed cards")
        if self.preset != "post_wall" and self.post_texts is not None:
            raise ValueError(f"{self.preset} does not accept post text")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy_defaults(self, handler):
        data = handler(self)
        if data.get("intensity") == "standard":
            data.pop("intensity", None)
        if data.get("position") == "center":
            data.pop("position", None)
        for name in ("cursor_start_x", "cursor_start_y", "cursor_end_x", "cursor_end_y", "click", "letter_text", "comment_text", "post_texts"):
            if data.get(name) is None:
                data.pop(name, None)
        return data


def append_visual_beats(graph, plan, *, width, height):
    cues = plan.finishing.visual_beats if plan.finishing else []
    if not cues:
        return graph
    parts, captions = graph.split(";"), None
    # Apply effects below captions, even after the B-roll/picture-layer pass.
    for i, part in enumerate(parts):
        match = re.fullmatch(r"\[([A-Za-z0-9_]+)\](subtitles=.*)\[vout\]", part)
        if match:
            captions = match[2]
            parts[i] = f"[{match[1]}]null[vout]"
            break
    parts = [p.replace("[vout]", "[beatbase0]") for p in parts]
    for i, cue in enumerate(cues):
        active = f"gte(t,{cue.start:.3f})*lt(t,{cue.end:.3f})"
        base, target = f"beatbase{i}", f"beatbase{i+1}"
        if cue.preset == "impact_frame":
            edge_ratio, opacity = {
                "subtle": (.012, .72), "standard": (.018, .9), "strong": (.026, 1),
            }[cue.intensity]
            edge = max(2, round(min(width, height)*edge_ratio))
            parts.append(f"[{base}]drawbox=x=0:y=0:w=iw:h=ih:color=0xF4C95D@{opacity:g}:t={edge}:enable='{active}'[{target}]")
        elif cue.preset == "clone_row":
            # A triptych of the full recorded shot, not person segmentation.
            # Trim work to the requested window. PTS is restored before overlay.
            tile_w = max(2, width//6*2)
            height_ratio, shade = {
                "subtle": (.36, .5), "standard": (.42, .6), "strong": (.48, .68),
            }[cue.intensity]
            tile_h = max(2, round(height*height_ratio)//2*2)
            inset = max(0, round(height*.12))
            y = {"upper": str(inset), "center": "(H-h)/2", "lower": f"H-h-{inset}"}[cue.position]
            parts.append(f"[{base}]split=2[beatbed{i}][beatexcerpt{i}]")
            parts.append(f"[beatexcerpt{i}]trim=start={cue.start:.3f}:end={cue.end:.3f},setpts=PTS-STARTPTS,"
                         f"scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
                         f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=0x201A16,setsar=1,split=3[clone{i}a][clone{i}b][clone{i}c]")
            parts.append(f"[clone{i}a][clone{i}b][clone{i}c]hstack=inputs=3,setpts=PTS+{cue.start:.3f}/TB[clonerow{i}]")
            parts.append(f"[beatbed{i}]drawbox=x=0:y=0:w=iw:h=ih:color=black@{shade:g}:t=fill:enable='{active}'[clonebed{i}]")
            parts.append(f"[clonebed{i}][clonerow{i}]overlay=x=(W-w)/2:y={y}:eof_action=pass:repeatlast=0:enable='{active}'[{target}]")
        else:
            # Typography/pointer effects are ASS treatments below dialogue captions.
            parts.append(f"[{base}]null[{target}]")
    parts.append(f"[beatbase{len(cues)}]{captions or 'null'}[vout]")
    return ";".join(parts)
