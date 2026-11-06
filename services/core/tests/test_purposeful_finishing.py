import array
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app import worker
from app.creative_selection import bound_generated_treatments, only_creative_treatments, remove_graphic_effects
from app.creative_treatments import Callout
from app.edit_plan import TalkingHeadEditPlan, repair_predictable_plan_defaults, schema_for_recipe, validate_edit_plan
from app.edit_renderer import _render_video, render_ass
from app.editor_provider import _model_content
from app.finishing_renderer import finishing_manifest
from app.finishing_tools import FinishingTools, finish_caption_events


def fixture():
    identity=str(uuid4())
    plan=TalkingHeadEditPlan(schema_version="1.5",recipe="talking_head",caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1",end_card="none",editorial_summary="Keep the recorded explanation.",
        clips=[dict(asset_id=identity,source_in=0,source_out=2,crop="center_fill",visual_preset="punch_in"),
               dict(asset_id=identity,source_in=2,source_out=4,crop="center_fill",transition="cross_dissolve")],
        finishing=FinishingTools(motions=[dict(clip_index=0,points=[dict(time=0),dict(time=2,zoom=1.2,x=.7)])],
            caption_regions=[dict(start=1,end=2,position="upper")]))
    asset=dict(asset_id=identity,has_video=True,has_audio=True,duration_seconds=30)
    return plan,asset


class PurposefulFinishingTests(unittest.TestCase):
    def test_effects_off_keeps_camera_and_caption_tools_without_decorative_cues(self):
        plan,asset=fixture()
        plan.finishing.callouts.append(Callout(start=0,end=1,text="A label"))
        context=dict(job=dict(recipe="talking_head",effect_level="off"),
            project=dict(privacy_mode="transcript_only"),assets=[asset])
        changed=bound_generated_treatments(context,plan)
        self.assertEqual(changed.finishing.callouts,[])
        self.assertEqual(changed.finishing.motions,plan.finishing.motions)
        self.assertEqual(changed.finishing.caption_regions,plan.finishing.caption_regions)
        prompt=_model_content(context,SimpleNamespace(editor_max_context_characters=120000))[0]["text"]
        self.assertIn("Camera and caption placement remain available",prompt)
        self.assertIn("leave finishing.callouts, finishing.pointers and finishing.music_regions empty",prompt)

    def test_planner_schema_has_strict_nested_camera_and_caption_controls(self):
        for recipe in ("talking_head","montage"):
            schema=schema_for_recipe(recipe)
            self.assertNotIn('"$ref"',json.dumps(schema))
            self.assertNotIn('"$defs"',json.dumps(schema))
            def check(node):
                if isinstance(node,dict):
                    if node.get("type")=="object":
                        self.assertIs(node["additionalProperties"],False)
                        self.assertEqual(set(node["required"]),set(node["properties"]))
                    for value in node.values(): check(value)
                elif isinstance(node,list):
                    for value in node: check(value)
            check(schema)
            tools=schema["properties"]["finishing"]["anyOf"][1]["properties"]
            self.assertIn("points",tools["motions"]["items"]["properties"])
            self.assertIn("position",tools["caption_regions"]["items"]["properties"])

    def test_generated_anchor_replaces_double_zoom_without_changing_speech(self):
        plan,asset=fixture()
        before=plan.model_dump(mode="json")
        result=bound_generated_treatments({"job":{"effect_level":"social"}},plan)
        self.assertEqual(result.clips[0].visual_preset,"standard")
        self.assertEqual(result.finishing,plan.finishing)
        self.assertEqual([(c.source_in,c.source_out) for c in result.clips],[(0,2),(2,4)])
        validate_edit_plan(result.model_dump(mode="json"),[asset])
        self.assertEqual(plan.model_dump(mode="json"),before)

    def test_default_framing_respects_anchor_and_new_transitions_keep_frozen_plans(self):
        plan,asset=fixture()
        plan.clips=plan.clips[:1]
        plan.clips[0].source_out=22
        plan.clips[0].visual_preset="standard"
        plan.finishing.motions[0].points[-1].time=22
        changed,_=repair_predictable_plan_defaults(plan.model_dump(mode="json"),
            creative_direction={"edit_style":"high_impact"},complete_creative_defaults=True)
        self.assertEqual(changed["clips"][0]["visual_preset"],"standard")
        validate_edit_plan(changed,[asset],creative_direction={"edit_style":"high_impact"})
        plan.clips[0].source_out=10
        plan.finishing=None
        plan.clips.append(plan.clips[0].model_copy(update={"source_in":10,"source_out":22,"story_role":"ending"}))
        document=plan.model_dump(mode="json")
        updated,_=repair_predictable_plan_defaults(document,creative_direction={"edit_style":"energetic"},complete_creative_defaults=True)
        self.assertEqual(updated["clips"][1]["transition"],"cut")
        legacy,_=repair_predictable_plan_defaults(document,creative_direction={"edit_style":"energetic"})
        self.assertEqual(legacy["clips"][1]["transition"],"cut")

    def test_caption_regions_and_motion_survive_word_safe_timeline_changes(self):
        from app.edit_plan import apply_timeline_adjustments
        plan,asset=fixture()
        self.assertTrue(only_creative_treatments(plan.finishing))
        events=finish_caption_events([dict(start=0,end=4,text="Recorded words")],plan.finishing)
        self.assertEqual([(e["start"],e["end"],e.get("position")) for e in events],[(0,1,None),(1,2,"upper"),(2,4,None)])
        changed=apply_timeline_adjustments(plan,[dict(clip_index=0,source_in=.5)],[asset])
        self.assertEqual(changed.finishing.caption_regions[0].start,.5)
        self.assertEqual(changed.finishing.motions[0].points[0].time,0)
        self.assertEqual(changed.finishing.motions[0].points[-1].time,1.5)

    def test_effect_removal_clears_labels_and_pointers_preserving_local_layout(self):
        plan,_=fixture()
        plan.finishing.callouts.append(Callout(start=0,end=1,text="Recorded term"))
        changed=remove_graphic_effects(plan)
        self.assertEqual(changed.finishing.callouts,[])
        self.assertEqual(changed.finishing.motions,plan.finishing.motions)
        self.assertEqual(changed.finishing.caption_regions,plan.finishing.caption_regions)
        self.assertTrue(plan.finishing.callouts)

    def test_timeline_reports_actual_tools_and_never_changes_saved_plan(self):
        plan,asset=fixture()
        original=plan.model_dump(mode="json")
        report=finishing_manifest({"job":{},"assets":[asset]},plan)["treatment_timeline"]
        self.assertEqual(report["additional_model_calls"],0)
        self.assertTrue(any(e["label"]=="Anchored camera move" and e["start"]==0 for e in report["events"]))
        self.assertTrue(any(e["kind"]=="captions" and (e["start"],e["end"])==(1,2) for e in report["events"]))
        self.assertTrue(any(e["label"]=="Short picture dissolve" and e["start"]==2 for e in report["events"]))
        self.assertEqual(report["basis"],"saved_plan_not_pixel_measurement")
        self.assertEqual(plan.model_dump(mode="json"),original)

    def test_worker_plans_once_and_keeps_agent_tools_through_validation(self):
        plan,asset=fixture()
        run=dict(id=uuid4(),job_id=uuid4(),version=1,edit_plan_id=None)
        context=dict(ready_for_editing=True,project=dict(name="Fixture",brief="Use the explanation.",privacy_mode="transcript_only",ai_copy_allowed=False),
            job=dict(recipe="talking_head",effect_level="social",edit_style="clean"),assets=[asset],music_library=[],creative_effect_library=[])
        planner=Mock(return_value=(plan,{"provider":"chatgpt_plan","model":"fixture"}))
        renderer=Mock(return_value={"outputs":{"preview":"fixture.mp4"},"manifest_path":"fixture.json"})
        database=MagicMock()
        with patch.multiple(worker,claim_pending_edit=Mock(return_value=run),build_editor_context=Mock(return_value=context),
            connection=Mock(return_value=database),create_edit_plan=planner,assert_ai_budget=Mock(),_persist_generated_plan=Mock(),render_edit_preview=renderer):
            worker.process_one_edit(worker.WorkerState())
        planner.assert_called_once()
        renderer.assert_called_once()
        rendered=renderer.call_args.args[1]
        self.assertEqual(rendered.clips[0].visual_preset,"standard")
        self.assertEqual(rendered.finishing.caption_regions[0].position,"upper")
        self.assertEqual([(c.source_in,c.source_out) for c in rendered.clips],[(0,2),(2,4)])


@unittest.skipUnless(shutil.which("ffmpeg"),"ffmpeg required for real finishing playback fixture")
class AgentFinishingRenderTests(unittest.TestCase):
    def test_agent_anchor_caption_region_and_dissolve_render_without_slowing_picture_or_voice(self):
        def ffmpeg(*args):
            return subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",*args],check=True,capture_output=True,timeout=60).stdout
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source,output,ass=root/"source.mp4",root/"finished.mp4",root/"captions.ass"
            ffmpeg("-f","lavfi","-i","color=c=blue:s=180x320:r=60:d=4,drawbox=x=0:y=0:w=80:h=320:color=red:t=fill",
                "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=4","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(source))
            plan,_=fixture()
            plan.finishing.motions[0].points[0].x=.2
            plan=bound_generated_treatments({"job":{"effect_level":"social"}},plan)
            events=finish_caption_events([dict(start=0,end=4,text="Recorded words")],plan.finishing)
            ass.write_text(render_ass(events,width=180,height=320))
            _render_video([(source,0,2),(source,2,4)],plan,ass,output,60,width=180,height=320)
            frames={}
            def picture(at):
                if at not in frames:
                    frames[at]=ffmpeg("-ss",str(at),"-i",str(output),"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1")
                return frames[at]
            def pixel(at):
                raw=picture(at)
                offset=(10*180+80)*3
                return tuple(raw[offset:offset+3])
            def colour_patch(at):
                raw=picture(at)
                return tuple(sum(raw[(y*180+x)*3+c] for y in range(5,15) for x in range(60,90))/300 for c in range(3))
            # The old x=80 probe was exactly on the red/blue boundary: NVENC
            # changed blue by 99 while x264 changed it by 106. A small region
            # measures the actual anchored framing change without that alias.
            before,after=colour_patch(.1),colour_patch(1.8)
            self.assertGreater(before[0]-after[0],40)
            self.assertGreater(after[2]-before[2],40)
            self.assertGreater(max(pixel(2.05)),100,"the dissolve must not introduce black")
            pcm=array.array('h',ffmpeg("-i",str(output),"-vn","-ac","1","-ar","8000","-f","s16le","pipe:1"))
            self.assertAlmostEqual(len(pcm)/8000,4,delta=.12)
            self.assertGreater(max(abs(v) for v in pcm),500)
