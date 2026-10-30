"""Small local visual/audio treatments; never change recorded speech timing."""

from typing import Literal

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
    style: Literal["label", "thought", "counter"] = "label"
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


def treatment_events(tools, width, height, captions=(), caption_position="lower_safe"):
    """ASS events share the caption pass, below dialogue captions (layer 0)."""
    if tools is None:
        return ""
    lines = []

    def event(cue, tags, text):
        lines.append(
            f"Dialogue: -1,{_timestamp(cue.start)},{_timestamp(cue.end)},GMBlue,,0,0,0,,{{{tags}}}{text}"
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
                "upper",
            )
        y = round(
            height * {"upper": 0.20, "middle": 0.42, "lower_safe": 0.60}[position]
        )
        # Bound line width for 64-character labels without arbitrary ASS input.
        words, rows, row = cue.text.split(), [], ""
        for word in words:
            if len(row) + len(word) > 25 and row:
                rows.append(row)
                row = ""
            row = (row + " " + word).strip()
        rows.append(row)
        longest = max(map(len, rows))
        size = max(
            10,
            min(
                round(min(width, height) * 0.055),
                round(width * 0.78 / max(1, longest) / 0.62),
            ),
        )
        tags = f"\\an5\\fnDejaVu Sans\\fs{size}\\b1\\bord2\\shad1\\1c&HFFFFFF&\\3c&H263A32&"
        if cue.style == "thought":
            tags += "\\i1"
        if cue.style == "counter":
            tags += "\\1c&H60DAFF&"
        tags += f"\\pos({width // 2},{y})"
        if cue.animation == "pop":
            tags += "\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)"
        if cue.animation == "slide_up":
            tags = tags.replace(
                f"\\pos({width // 2},{y})",
                f"\\move({width // 2},{y + height * 0.025:.0f},{width // 2},{y},0,180)",
            )
        tags += "\\fad(60,80)"
        event(cue, tags, r"\N".join(rows))
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
    return "\n".join(lines) + ("\n" if lines else "")
