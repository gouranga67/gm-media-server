"""Small native picture treatments. One picture clock, original audio untouched."""

import re
from typing import Literal
from pydantic import model_validator
from app.creative_treatments import TreatmentWindow


class VisualBeat(TreatmentWindow):
    preset: Literal["impact_frame", "clone_row"]

    @model_validator(mode="after")
    def short_beat(self):
        maximum = .25 if self.preset == "impact_frame" else 2.5
        if self.end - self.start > maximum + .0001:
            raise ValueError(f"{self.preset} must last at most {maximum:g} seconds")
        return self


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
            edge = max(2, round(min(width, height)*.018))
            parts.append(f"[{base}]drawbox=x=0:y=0:w=iw:h=ih:color=0xF4C95D@0.9:t={edge}:enable='{active}'[{target}]")
        else:
            # A triptych of the full recorded shot, not person segmentation.
            # Trim work to the requested window. PTS is restored before overlay.
            tile_w = max(2, width//6*2)
            tile_h = max(2, round(height*.42)//2*2)
            parts.append(f"[{base}]split=2[beatbed{i}][beatexcerpt{i}]")
            parts.append(f"[beatexcerpt{i}]trim=start={cue.start:.3f}:end={cue.end:.3f},setpts=PTS-STARTPTS,"
                         f"scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
                         f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=0x201A16,setsar=1,split=3[clone{i}a][clone{i}b][clone{i}c]")
            parts.append(f"[clone{i}a][clone{i}b][clone{i}c]hstack=inputs=3,setpts=PTS+{cue.start:.3f}/TB[clonerow{i}]")
            parts.append(f"[beatbed{i}]drawbox=x=0:y=0:w=iw:h=ih:color=black@0.6:t=fill:enable='{active}'[clonebed{i}]")
            parts.append(f"[clonebed{i}][clonerow{i}]overlay=x=(W-w)/2:y=(H-h)/2:eof_action=pass:repeatlast=0:enable='{active}'[{target}]")
    parts.append(f"[beatbase{len(cues)}]{captions or 'null'}[vout]")
    return ";".join(parts)
