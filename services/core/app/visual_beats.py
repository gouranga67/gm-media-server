"""Small native picture treatments. One picture clock, original audio untouched."""

import re
from typing import Literal
from pydantic import Field, field_validator, model_serializer, model_validator
from app.creative_treatments import TreatmentWindow
from app.effect_registry import effect_definition


class VisualBeat(TreatmentWindow):
    preset: Literal["impact_frame", "clone_row", "live_cursor", "letter_dive", "comment_drop", "voice_note", "post_wall", "sketch_words", "rack_focus", "paper_tear"]
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
    sketch_text: str | None = Field(default=None, min_length=1, max_length=24)
    focus_start_x: float | None = Field(default=None, ge=.3, le=.7)
    focus_start_y: float | None = Field(default=None, ge=.18, le=.82)
    focus_end_x: float | None = Field(default=None, ge=.3, le=.7)
    focus_end_y: float | None = Field(default=None, ge=.18, le=.82)
    boundary_index: int | None = Field(default=None, ge=1, le=47)
    tear_direction: Literal["left", "right"] | None = None

    @field_validator("letter_text", "comment_text", "sketch_text")
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
        if self.preset == "sketch_words":
            if self.sketch_text is None:
                raise ValueError("sketch_words requires source-backed words")
            if len(self.sketch_text.split()) > 3:
                raise ValueError("sketch_words accepts at most three words")
        elif self.sketch_text is not None:
            raise ValueError(f"{self.preset} does not accept sketch text")
        focus_values = (self.focus_start_x, self.focus_start_y, self.focus_end_x, self.focus_end_y)
        if self.preset == "rack_focus":
            if any(value is None for value in focus_values):
                raise ValueError("rack_focus requires bounded start and end coordinates")
            distance = ((self.focus_end_x - self.focus_start_x) ** 2 + (self.focus_end_y - self.focus_start_y) ** 2) ** .5
            if distance < .08:
                raise ValueError("rack_focus points must identify a visible focus move")
        elif any(value is not None for value in focus_values):
            raise ValueError(f"{self.preset} does not accept focus coordinates")
        if self.preset == "paper_tear":
            if self.boundary_index is None or self.tear_direction is None:
                raise ValueError("paper_tear requires a clip boundary and pull direction")
        elif self.boundary_index is not None or self.tear_direction is not None:
            raise ValueError(f"{self.preset} does not accept paper tear parameters")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy_defaults(self, handler):
        data = handler(self)
        if data.get("intensity") == "standard":
            data.pop("intensity", None)
        if data.get("position") == "center":
            data.pop("position", None)
        for name in ("cursor_start_x", "cursor_start_y", "cursor_end_x", "cursor_end_y", "click", "letter_text", "comment_text", "post_texts", "sketch_text", "focus_start_x", "focus_start_y", "focus_end_x", "focus_end_y", "boundary_index", "tear_direction"):
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
        elif cue.preset == "rack_focus":
            # Honest simulated rack focus: a sharp source window moves over a
            # softly blurred copy. There is no depth estimation or tracking.
            blur, width_ratio, height_ratio = {
                "subtle": (4, .66, .40),
                "standard": (8, .58, .34),
                "strong": (12, .50, .30),
            }[cue.intensity]
            patch_w = max(2, round(width * width_ratio) // 2 * 2)
            patch_h = max(2, round(height * height_ratio) // 2 * 2)
            duration = cue.end - cue.start
            progress = f"min(max((t-{cue.start:.3f})/{duration:.3f}\\,0)\\,1)"
            centre_x = f"({cue.focus_start_x:.4f}+({cue.focus_end_x-cue.focus_start_x:.4f})*{progress})"
            centre_y = f"({cue.focus_start_y:.4f}+({cue.focus_end_y-cue.focus_start_y:.4f})*{progress})"
            crop_x = f"iw*{centre_x}-ow/2"
            crop_y = f"ih*{centre_y}-oh/2"
            overlay_x = f"W*{centre_x}-w/2"
            overlay_y = f"H*{centre_y}-h/2"
            ramp = min(.18, duration / 5)
            parts.append(f"[{base}]split=3[focusbed{i}][focusblurinput{i}][focussharp{i}]")
            parts.append(
                f"[focusblurinput{i}]gblur=sigma={blur}:steps=2,format=yuva420p,"
                f"fade=t=in:st={cue.start:.3f}:d={ramp:.3f}:alpha=1,"
                f"fade=t=out:st={cue.end-ramp:.3f}:d={ramp:.3f}:alpha=1[focusblur{i}]"
            )
            parts.append(
                f"[focusbed{i}][focusblur{i}]overlay=x=0:y=0:eof_action=pass:repeatlast=0:enable='{active}'[focussoft{i}]"
            )
            parts.append(
                f"[focussharp{i}]crop=w={patch_w}:h={patch_h}:x='{crop_x}':y='{crop_y}'[focuspatch{i}]"
            )
            parts.append(
                f"[focussoft{i}][focuspatch{i}]overlay=x='{overlay_x}':y='{overlay_y}':"
                f"eof_action=pass:repeatlast=0:enable='{active}'[{target}]"
            )
        elif cue.preset == "paper_tear":
            # Freeze the final outgoing frame and pull it away in staggered
            # horizontal paper strips. The already assembled next clip remains
            # underneath, and the separately assembled audio is never touched.
            strips, edge, stagger_ratio = {
                "subtle": (5, 2, .10),
                "standard": (7, 3, .14),
                "strong": (9, 4, .18),
            }[cue.intensity]
            duration = cue.end - cue.start
            sample_start = max(0, cue.start - .1)
            labels = "".join(f"[tearstrip{i}_{strip}]" for strip in range(strips))
            parts.append(f"[{base}]split=2[tearbed{i}][tearoutgoing{i}]")
            parts.append(
                f"[tearoutgoing{i}]trim=start={sample_start:.3f}:end={cue.start:.3f},reverse,"
                f"trim=end_frame=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={duration:.3f},"
                f"trim=duration={duration:.3f},setpts=PTS+{cue.start:.3f}/TB,split={strips}{labels}"
            )
            current = f"tearbed{i}"
            for strip in range(strips):
                y = height * strip // strips
                next_y = height * (strip + 1) // strips
                strip_h = next_y - y
                # A deterministic alternating delay makes the exposed edge
                # irregular without random or generated imagery.
                delay = duration * stagger_ratio * ((strip * 3) % strips) / max(1, strips - 1)
                travel = max(.1, duration - delay)
                progress = f"min(max((t-{cue.start + delay:.3f})/{travel:.3f}\\,0)\\,1)"
                x = f"-w*{progress}" if cue.tear_direction == "left" else f"W*{progress}"
                edge_x = f"iw-{edge}" if cue.tear_direction == "left" else "0"
                piece = f"tearpiece{i}_{strip}"
                next_base = target if strip == strips - 1 else f"tearstage{i}_{strip}"
                parts.append(
                    f"[tearstrip{i}_{strip}]crop=w={width}:h={strip_h}:x=0:y={y},"
                    f"drawbox=x={edge_x}:y=0:w={edge}:h=ih:color=0xF7F1E3@0.96:t=fill[{piece}]"
                )
                parts.append(
                    f"[{current}][{piece}]overlay=x='{x}':y={y}:eof_action=pass:repeatlast=0:"
                    f"enable='{active}'[{next_base}]"
                )
                current = next_base
        else:
            # Typography/pointer effects are ASS treatments below dialogue captions.
            parts.append(f"[{base}]null[{target}]")
    parts.append(f"[beatbase{len(cues)}]{captions or 'null'}[vout]")
    return ";".join(parts)
