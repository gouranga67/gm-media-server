#!/usr/bin/env python3
"""Render a synthetic typography/effects sample. No AI, originals or database."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/core"))
from app.edit_renderer import _render_video, render_ass
from app.effect_registry import EFFECT_REGISTRY_VERSION
from app.edit_plan import TalkingHeadEditPlan
from app.finishing_tools import FinishingTools
from app.render_integrity import rendered_audio_packet_error


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    source,ass,output=(root/name for name in ('synthetic-source.mp4','captions.ass','caption-and-effects-preview.mp4'))
    def ff(*args):
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',*args],check=True,timeout=120,capture_output=True)
    # An abstract stand-in, deliberately not generated/replacement footage.
    ff('-f','lavfi','-i',"color=c=0x8C7765:s=540x960:r=30:d=7,drawbox=x=0:y=0:w=540:h=440:c=0xBDB5A5:t=fill,drawbox=x=160:y=400:w=220:h=420:c=0x254050:t=fill,drawbox=x=210:y=300:w=120:h=140:c=0xD0AD89:t=fill",
       '-f','lavfi','-i','sine=frequency=220:sample_rate=48000:duration=7','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source))
    tools=FinishingTools(callouts=[dict(start=.2,end=1.5,text='A stronger first impression',style='headline'),
        dict(start=2,end=4.6,text='$40 million in client revenue',style='headline')],
        visual_beats=[dict(start=1.6,end=1.8,preset='impact_frame',intensity='strong'),
                      dict(start=5,end=6.7,preset='clone_row',intensity='subtle',position='upper')])
    plan=TalkingHeadEditPlan(schema_version='1.5',recipe='talking_head',clips=[dict(asset_id=uuid4(),source_in=0,source_out=7,crop='center_fill')],
        caption_style='clean_blue_v1',audio_preset='spoken_voice_v1',end_card='none',editorial_summary='Synthetic graphics and timing demonstration.',finishing=tools)
    events=[dict(start=0,end=1.5,text="Here’s what we’ve built."),dict(start=2,end=3.2,text='Generated 40 million dollars'),dict(start=3.2,end=4.6,text='in revenue for clients.'),dict(start=5,end=6.7,text='Three shots. One audio track.')]
    ass.write_text(render_ass(events,treatments=tools),encoding='utf-8')
    started=time.monotonic()
    encoder=_render_video([(source,0,7)],plan,ass,output,120)
    error=rendered_audio_packet_error(output,60)
    if error:raise RuntimeError(error)
    for t,name in ((2.6,'headline-frame.png'),(5.8,'clone-row-frame.png')):
        ff('-ss',str(t),'-i',str(output),'-frames:v','1',str(root/name))
    report=dict(status='passed',synthetic_demo=True,encoder=encoder,render_seconds=round(time.monotonic()-started,2),
        duration_seconds=7,width=540,height=960,hosted_model_calls=0,audio_packet_timing_verified=True,
        native_effect_registry_version=EFFECT_REGISTRY_VERSION,effects=['impact_frame','clone_row'])
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    source.unlink()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
