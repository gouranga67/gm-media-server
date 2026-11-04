import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan, derive_duration_variant, schema_for_recipe
from app.finishing_tools import FinishingTools, validate_finishing, retime_finishing
from app.stabilization import clip_choices, stabilization_filter, stabilization_manifest
from app.edit_renderer import _ffmpeg_filter as speech_graph, render_ass
from app.montage_renderer import _filter_graph as montage_graph


def plan_for(montage=False, count=1, **tools):
    clips = [dict(asset_id=uuid4(),source_in=0,source_out=3,crop="center_fill") for _ in range(max(count, 2 if montage else 1))]
    if montage:
        clips = [c | dict(media_kind="video",duration=3,include_source_audio=True) for c in clips]
    cls = MontageEditPlan if montage else TalkingHeadEditPlan
    options = dict(audio_preset="montage_mix_v1") if montage else dict(audio_preset="spoken_voice_v1",caption_style="clean_blue_v1")
    return cls(schema_version="1.5",recipe="montage" if montage else "talking_head",
        end_card="none",editorial_summary="Keep the recording intact.",clips=clips,finishing=FinishingTools(**tools),**options)



class StabilizationTests(unittest.TestCase):
    def test_default_serialization_and_hosted_schema_stay_unchanged(self):
        self.assertNotIn("stabilize_clips",FinishingTools().model_dump(mode="json"))
        for recipe in ("talking_head","montage"):
            self.assertNotIn("stabilize_clips",json.dumps(schema_for_recipe(recipe)))
        plan=plan_for()
        self.assertEqual(stabilization_filter(plan,0,540,960,30),"")
        self.assertFalse(stabilization_manifest(plan)["quality_verified"])

    def test_only_unique_existing_bounded_normal_speed_video_clips_are_allowed(self):
        for values in ([0]*2, [0,1,2,3,4], [-1], [48], [True], ["0"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_finishing(plan_for(stabilize_clips=values),[])
        for montage in (False,True):
            plan=plan_for(montage,stabilize_clips=[0]);validate_finishing(plan,[])
            plan.clips[0].source_out=9
            if montage:plan.clips[0].duration=9
            with self.assertRaisesRegex(ValueError,"1–8"):
                validate_finishing(plan,[])
        plan=plan_for(True,stabilize_clips=[0]);plan.clips[0].duration=2
        with self.assertRaisesRegex(ValueError,"Retimed"):
            validate_finishing(plan,[])
        plan.clips[0].media_kind="image"
        with self.assertRaisesRegex(ValueError,"Photos"):
            validate_finishing(plan,[])

    def test_manual_anchors_and_face_follow_are_not_combined_with_stabilization(self):
        plan=plan_for(stabilize_clips=[0],smart_framing="face")
        with self.assertRaisesRegex(ValueError,"single-face"):
            validate_finishing(plan,[])
        plan=plan_for(stabilize_clips=[0],motions=[dict(clip_index=0,points=[dict(time=0,zoom=1.1)])])
        self.assertFalse(clip_choices(plan.model_dump(mode="json"))[0]["eligible"])
        with self.assertRaisesRegex(ValueError,"Manual"):
            validate_finishing(plan,[])

    def test_timeline_edits_clear_selection_and_approved_prefix_keeps_surviving_shots(self):
        plan=plan_for(count=2,stabilize_clips=[0,1])
        tools=retime_finishing(plan.finishing,[[0,6,0]],plan.clips,[(0,0,3),(1,0,3)])
        self.assertEqual(tools.stabilize_clips,[])
        variant=derive_duration_variant(plan,4)
        self.assertEqual(variant.finishing.stabilize_clips,[0,1])
        validate_finishing(variant,[])
        short=derive_duration_variant(plan,3.5)
        self.assertEqual(short.finishing.stabilize_clips,[0])
        self.assertEqual(plan.finishing.stabilize_clips,[0,1])

    def test_graph_changes_only_selected_video_branches_and_never_audio(self):
        for montage in (False,True):
            plan=plan_for(montage,count=2,stabilize_clips=[1])
            graph=self.graph(plan,Path("captions.ass"),320,180)
            plain=self.graph(plan.model_copy(update={"finishing":FinishingTools()}),Path("captions.ass"),320,180)
            self.assertEqual(graph.count("deshake="),1)
            self.assertNotIn("deshake",graph.split(";",1)[0])
            self.assertEqual([s for s in graph.split(';') if s.startswith(('[0:a','[1:a'))],
                [s for s in plain.split(';') if s.startswith(('[0:a','[1:a'))])
            self.assertIn("rx=32:ry=32",stabilization_filter(plan,1,1080,1920,30))
            report=stabilization_manifest(plan)
            self.assertEqual(report["clip_indexes"],[1]);self.assertEqual(report["hosted_model_calls"],0)

    @staticmethod
    def graph(plan,caption,width,height):
        if isinstance(plan,MontageEditPlan):
            return montage_graph(plan,{str(c.asset_id):dict(has_audio=True) for c in plan.clips},width=width,height=height,
                fps=30,music_input_index=None,captions_path=caption)
        return speech_graph(plan,caption,width=width,height=height,frames_per_second=30)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_renders_reduce_synthetic_jitter_preserve_frames_and_identical_audio(self):
        import numpy as np
        import cv2
        def run(args,**kwargs):
            return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,**kwargs).stdout
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);w,h=320,180
            # Unique high-contrast texture, shaken at 60fps. No natural-media or
            # subjective quality claim is inferred from this controlled fixture.
            base=np.random.default_rng(4).integers(0,256,(h,w,3),dtype=np.uint8)
            frames=[np.roll(base,(3 if (i//2)%2 else -3,5 if (i//2)%2 else -5),(0,1)) for i in range(180)]
            source=root/'shake.mkv'
            run(['ffmpeg','-v','error','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','60','-i','pipe:0',
                '-f','lavfi','-i','sine=frequency=700:sample_rate=48000:duration=3','-t','3','-c:v','ffv1','-c:a','pcm_s16le',str(source)],input=b''.join(f.tobytes() for f in frames))
            caption=root/'empty.ass';caption.write_text(render_ass([],width=w,height=h))
            def decode(path):
                raw=run(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-vsync','0','-f','rawvideo','-pix_fmt','gray','pipe:1'])
                pics=np.frombuffer(raw,np.uint8).reshape(-1,h,w)
                movements=[]
                for a,b in zip(pics[10:-1],pics[11:]):
                    delta,response=cv2.phaseCorrelate(np.float32(a[30:-30,40:-40]),np.float32(b[30:-30,40:-40]))
                    if response>.1:movements.append(float(np.hypot(*delta)))
                return pics,float(np.median(movements))
            for montage in (False,True):
                outputs=[]
                for enabled in (False,True):
                    plan=plan_for(montage,stabilize_clips=list(range(2 if montage else 1)) if enabled else [])
                    output=root/f'{montage}-{enabled}.mkv';graph=self.graph(plan,caption,w,h)
                    run(['ffmpeg','-v','error','-nostdin','-filter_complex_threads','1',*[arg for _ in plan.clips for arg in ('-i',str(source))],'-filter_complex',graph,
                        '-map','[vout]','-map','[aout]','-vsync','0','-c:v','ffv1','-c:a','pcm_s16le',str(output)])
                    pics,jitter=decode(output)
                    self.assertEqual(len(pics),90 * len(plan.clips))
                    audio=run(['ffmpeg','-v','error','-i',str(output),'-map','0:a:0','-f','s16le','pipe:1'])
                    outputs.append((audio,jitter))
                self.assertEqual(outputs[0][0],outputs[1][0])
                self.assertGreater(outputs[0][1],8)
                self.assertLess(outputs[1][1],outputs[0][1]*.8,(montage,outputs[0][1],outputs[1][1]))
