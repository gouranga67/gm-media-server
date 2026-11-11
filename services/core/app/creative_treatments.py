"""Small local visual/audio treatments; never change recorded speech timing."""

from typing import Literal
import re

from app.caption_layout import caption_lines, text_width

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TreatmentWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: float = Field(ge=0, le=120)
    end: float = Field(gt=0, le=120)

    @model_validator(mode="after")
    def bounded(self):
        if not 0.1 <= self.end - self.start <= 8:
            raise ValueError("a creative treatment must last between 0.1 and 8 seconds")
        return self


class Callout(TreatmentWindow):
    text: str = Field(min_length=1, max_length=64)
    position: Literal["upper", "middle", "lower_safe"] = "upper"
    style: Literal["label", "thought", "counter", "headline", "comment"] = "label"
    animation: Literal["fade", "pop", "slide_up"] = "pop"

    @field_validator("text")
    @classmethod
    def plain_text(cls, text):
        if (
            not text.strip()
            or any(c in text for c in "{}\\")
            or any(ord(c) < 32 for c in text)
        ):
            raise ValueError(
                "callouts require plain text without subtitle commands or line breaks"
            )
        return text.strip()


class Pointer(TreatmentWindow):
    x: float = Field(default=0.75, ge=0.08, le=0.92)
    y: float = Field(default=0.35, ge=0.1, le=0.8)
    size: float = Field(default=0.14, ge=0.06, le=0.25)
    shape: Literal["circle", "arrow"] = "circle"
    direction: Literal["right", "left", "up", "down"] = "right"


class MusicRegion(TreatmentWindow):
    gain_db: float = Field(default=-60, ge=-60, le=0)


def music_region_filters(regions):
    """Smooth 40 ms ramps, applied only on the music branch before ducking."""
    # loudnorm may emit a whole short track as one large frame. Reframe to
    # 10 ms blocks so per-frame volume follows the requested reel times.
    filters = ["asetnsamples=n=480:p=0"] if regions else []
    for region in regions:
        fade = min(0.04, (region.end - region.start) / 4)
        gain = 0 if region.gain_db <= -60 else 10 ** (region.gain_db / 20)
        expression = (
            f"if(lt(t,{region.start:.3f}),1,"
            f"if(lt(t,{region.start + fade:.3f}),1-(1-{gain:.6f})*(t-{region.start:.3f})/{fade:.3f},"
            f"if(lt(t,{region.end - fade:.3f}),{gain:.6f},"
            f"if(lt(t,{region.end:.3f}),{gain:.6f}+(1-{gain:.6f})*(t-{region.end - fade:.3f})/{fade:.3f},1))))"
        )
        filters.append(f"volume='{expression}':eval=frame")
    return ",".join(filters)


def _timestamp(seconds):
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def treatment_events(tools, width, height, captions=(), caption_position="lower_safe", *, brand_kit=None):
    """ASS events share the caption pass, below dialogue captions (layer 0)."""
    if tools is None:
        return ""
    lines = []

    def event(cue, tags, text, layer=-1):
        lines.append(
            f"Dialogue: {layer},{_timestamp(cue.start)},{_timestamp(cue.end)},GMBlue,,0,0,0,,{{{tags}}}{text}"
        )

    for cue in tools.callouts:
        active_bands = {
            event.get("position") or caption_position
            for event in captions
            if event["start"] < cue.end and event["end"] > cue.start
        }
        position = cue.position
        if position in active_bands:
            position = next(
                (
                    band
                    for band in ("upper", "middle", "lower_safe")
                    if band not in active_bands
                ),
                None,
            )
        if position is None:
            continue  # Dialogue captions take priority when every band is busy.
        y = round(
            height * {"upper": 0.20, "middle": 0.42, "lower_safe": 0.60}[position]
        )
        accent = str((brand_kit or {}).get("accent_color") or "#F4C95D")
        red, green, blue = (int(accent[i:i+2], 16) for i in (1, 3, 5))
        colour = f"&H{blue:02X}{green:02X}{red:02X}&"
        unit = min(width, height) / 540
        max_width = width * .76
        headline = cue.style in {"label", "headline", "counter"}
        number = re.match(r"^([$£€]?\d[\d,.]*(?:\s+(?:million|billion|thousand)|\s*[%KMB])?)(?:\s+(.+))?$", cue.text, re.I) if headline else None
        rows = []
        if number and number[2]:
            lead = number[1].upper()
            size = max(10, round(48 * unit))
            while text_width(lead, "DejaVu Sans", size) > max_width and size > 10:
                size -= 1
            rows.append((lead, size, colour))
            tail, small = caption_lines(number[2].upper(), "DejaVu Sans", max(10, round(23*unit)), max_width)
            rows.extend((row, small, "&HFFFFFF&") for row in tail.splitlines())
        else:
            copy = cue.text.upper() if headline else cue.text
            copy, size = caption_lines(copy, "DejaVu Sans", max(10, round((35 if headline else 28)*unit)), max_width, minimum_scale=.3)
            rows.extend((row, size, colour if cue.style == "counter" else "&HFFFFFF&") for row in copy.splitlines())
        pad = max(4, round(15*unit))
        panel_width = round(max(text_width(t, "DejaVu Sans", s) for t,s,_ in rows)) + 2*pad
        panel_height = round(sum(s*1.24 for _,s,_ in rows)) + 2*pad
        x, top = (width-panel_width)//2, round(y-panel_height/2)

        def placement(cx, cy):
            tags = f"\\pos({cx},{cy})"
            if cue.animation == "slide_up":
                tags = f"\\move({cx},{cy+round(height*.02)},{cx},{cy},0,180)"
            # Alpha entrance leaves the panel and glyph metrics steady. The
            # pop emphasis belongs to the text, never a continuously bouncing card.
            return tags + "\\fad(90,100)"

        # Native ASS vector panel: no browser process, bitmap or extra input.
        panel = f"m 0 0 l {panel_width} 0 {panel_width} {panel_height} 0 {panel_height}"
        event(cue, "\\an7\\p1\\bord0\\shad0\\1c&H201A16&\\1a&H28&" + placement(x, top), panel, -3)
        stripe = f"m 0 0 l {max(2,round(4*unit))} 0 {max(2,round(4*unit))} {panel_height} 0 {panel_height}"
        event(cue, f"\\an7\\p1\\bord0\\shad0\\1c{colour}" + placement(x, top), stripe, -2)
        cursor = top + pad
        for copy, size, fill in rows:
            tags = f"\\an8\\fnDejaVu Sans\\fs{size}\\b1\\bord0.8\\shad0\\1c{fill}\\3c&H201A16&"
            if cue.style == "thought":
                tags += "\\i1"
            tags += placement(width//2, round(cursor))
            if cue.animation == "pop":
                tags += "\\fscx94\\fscy94\\t(0,130,\\fscx100\\fscy100)"
            event(cue, tags, copy)
            cursor += size*1.24
    for cue in tools.pointers:
        radius = max(4, round(width * cue.size / 2))
        tags = f"\\an7\\pos({width * cue.x - radius:.0f},{height * cue.y - radius:.0f})\\fad(80,80)\\shad0\\1c&H60DAFF&\\3c&H263A32&"
        if cue.shape == "circle":
            # Cubic Bezier circle, transparent fill and a visible outline.
            k = radius * 0.55228475
            r = radius
            path = (
                f"m {r} 0 b {r + k:.1f} 0 {2 * r} {r - k:.1f} {2 * r} {r} "
                f"{2 * r} {r + k:.1f} {r + k:.1f} {2 * r} {r} {2 * r} "
                f"{r - k:.1f} {2 * r} 0 {r + k:.1f} 0 {r} 0 {r - k:.1f} {r - k:.1f} 0 {r} 0"
            )
            tags += f"\\1a&HFF&\\bord{max(2, round(width * 0.006))}\\3c&H60DAFF&"
        else:
            # Tip points at x/y; rotate the vector around that point.
            tags = tags.replace(
                f"\\pos({width * cue.x - radius:.0f},{height * cue.y - radius:.0f})",
                f"\\pos({width * cue.x:.0f},{height * cue.y:.0f})",
            )
            angle = {"right": 0, "left": 180, "up": 90, "down": 270}[cue.direction]
            tags += f"\\bord1\\frz{angle}"
            path = f"m {-2 * radius} {-radius * 0.25:.1f} l {-radius} {-radius * 0.25:.1f} {-radius} {-radius * 0.6:.1f} 0 0 {-radius} {radius * 0.6:.1f} {-radius} {radius * 0.25:.1f} {-2 * radius} {radius * 0.25:.1f}"
        event(cue, tags + "\\p1", path)
    for cue in tools.visual_beats:
        if cue.preset == "letter_dive":
            text = cue.letter_text.upper()
            unit = min(width, height) / 540
            size = max(14, round({"subtle": 34, "standard": 43, "strong": 52}[cue.intensity] * unit))
            widths = [text_width(character, "DejaVu Sans", size, bold=True) for character in text]
            total_width = sum(widths)
            x = (width - total_width) / 2
            final_y = round(height * {"upper": .22, "center": .46, "lower": .70}[cue.position])
            travel = round(height * {"subtle": .08, "standard": .13, "strong": .18}[cue.intensity])
            stagger_span = min((cue.end - cue.start) * .38, .65)
            step = stagger_span / max(1, len(text) - 1)
            entrance_ms = max(140, round(min(.32, (cue.end - cue.start) * .4) * 1000))
            for index, character in enumerate(text):
                center_x = round(x + widths[index] / 2)
                x += widths[index]
                if character.isspace():
                    continue
                letter = cue.model_copy(update={"start": cue.start + index * step})
                tags = (
                    f"\\an5\\fnDejaVu Sans\\fs{size}\\b1\\move({center_x},{final_y-travel},{center_x},{final_y},0,{entrance_ms})"
                    "\\fad(30,90)\\fscx78\\fscy78"
                    f"\\t(0,{entrance_ms},\\fscx100\\fscy100)"
                    "\\1c&HFFFFFF&\\3c&H201A16&\\bord1.6\\shad1"
                )
                event(letter, tags, character, -1)
            continue
        if cue.preset != "live_cursor":
            continue
        scale = {"subtle": .75, "standard": 1, "strong": 1.3}[cue.intensity]
        unit = min(width, height) / 540 * scale
        start_x, start_y = round(width * cue.cursor_start_x), round(height * cue.cursor_start_y)
        end_x, end_y = round(width * cue.cursor_end_x), round(height * cue.cursor_end_y)
        duration_ms = max(1, round((cue.end - cue.start) * 1000))
        pointer = "m 0 0 l 0 30 7 23 14 39 20 36 13 20 26 20"
        tags = (
            f"\\an7\\move({start_x},{start_y},{end_x},{end_y},0,{duration_ms})"
            f"\\fad(40,80)\\fscx{100 * unit:.1f}\\fscy{100 * unit:.1f}"
            "\\1c&HFFFFFF&\\3c&H20211F&\\bord1.4\\shad0\\p1"
        )
        event(cue, tags, pointer, -1)
        if cue.click:
            pulse = cue.model_copy(update={"start": max(cue.start, cue.end - .28)})
            radius = max(5, round(13 * unit))
            k = radius * .55228475
            circle = (
                f"m {radius} 0 b {radius + k:.1f} 0 {2 * radius} {radius - k:.1f} {2 * radius} {radius} "
                f"{2 * radius} {radius + k:.1f} {radius + k:.1f} {2 * radius} {radius} {2 * radius} "
                f"{radius - k:.1f} {2 * radius} 0 {radius + k:.1f} 0 {radius} 0 {radius - k:.1f} "
                f"{radius - k:.1f} 0 {radius} 0"
            )
            pulse_tags = (
                f"\\an7\\pos({end_x - radius},{end_y - radius})\\fad(20,100)"
                "\\1a&HFF&\\3c&H60DAFF&\\bord2\\shad0\\fscx55\\fscy55"
                "\\t(0,220,\\fscx125\\fscy125)\\p1"
            )
            event(pulse, pulse_tags, circle, -2)
    return "\n".join(lines) + ("\n" if lines else "")
