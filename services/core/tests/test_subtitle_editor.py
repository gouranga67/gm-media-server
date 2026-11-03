from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from app import subtitle_editor as api
from app.edit_plan import TalkingHeadEditPlan, derive_duration_variant
from app.edit_renderer import render_ass, render_webvtt, _render_video
from app.subtitle_document import (SubtitleCue, SubtitleEdit, basis, corrected_document, fingerprint,
    make_document, matches, parse_ass, resolve_events, validate_cues)


def plan():
    return TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head", clips=[
        dict(asset_id=uuid4(),source_in=0,source_out=3,crop="center_fill"),
        dict(asset_id=uuid4(),source_in=0,source_out=3,crop="center_fill")],
        caption_style="clean_blue_v1",audio_preset="spoken_voice_v1",end_card="none",editorial_summary="A saved source story.")


def events():
    return [dict(start=.1,end=2.5,text="Costa Royal!"), dict(start=3.2,end=5.8,text="Our favourite cream.")]


def row():
    p=plan().model_dump(mode="json")
    return dict(id=uuid4(),job_id=uuid4(),edit_plan_id=uuid4(),status="ready",version=2,
        plan_document=p,manifest={"subtitle_events":events()},caption_corrections=[],duration_policy={"duration_mode":"strict","max_duration_seconds":60})


class SubtitleDocumentTests(unittest.TestCase):
    def test_plain_text_changes_do_not_touch_source_plan_or_timing(self):
        p=plan(); before=p.model_dump(mode="json")
        doc=make_document(before,events())
        doc["cues"][0]["text"]="Castor oil!"
        output=resolve_events({"_subtitle_document":doc},p,events())
        self.assertEqual(output[0],dict(start=.1,end=2.5,text="Castor oil!"))
        self.assertEqual(p.model_dump(mode="json"),before)

    def test_hidden_and_positioned_cues_are_used_by_ass_and_vtt(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        doc["cues"][0].update(hidden=True)
        doc["cues"][1].update(position="upper",text="Correct cream")
        output=resolve_events({"_subtitle_document":doc},p,events())
        ass=render_ass(output); vtt=render_webvtt(output)
        self.assertNotIn("Costa",ass+vtt)
        self.assertIn(r"\an8",ass)
        self.assertIn("Correct cream",vtt)

    def test_short_position_regions_and_offset_tails_do_not_break_the_editor(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),[
            dict(start=1,end=1.02,text="Short region",position="upper"),
            dict(start=5.8,end=6.3,text="Last word"),dict(start=6.1,end=6.4,text="Not visible")])
        self.assertEqual(len(doc["cues"]),2)
        self.assertEqual(doc["cues"][-1]["end"],6)
        self.assertEqual(len(validate_cues(doc["cues"],6)),2)
        self.assertEqual(len(resolve_events({"_subtitle_document":doc},p,[])),2)

    def test_user_ass_control_text_is_escaped(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        doc["cues"][0]["text"]=r"{\pos(1,1)} <script> oil"
        ass=render_ass(resolve_events({"_subtitle_document":doc},p,events()))
        self.assertIn(r"\{\\pos(1,1)\}",ass)

    def test_legacy_ass_round_trip_reads_only_spoken_caption_layer(self):
        raw=[dict(start=.1,end=2.5,text=r"Review {nice}, a \ path",position="upper")]
        ass=render_ass(raw)+"Dialogue: 3,0:00:00.00,0:00:01.00,Callout,,0,0,0,,Not speech\n"
        self.assertEqual(parse_ass(ass),raw)

    def test_caption_text_updates_are_not_applied_twice_on_exact_rebuild(self):
        doc=make_document(plan().model_dump(mode="json"),events())
        correction=dict(original_text="oil",replacement_text="castor oil")
        doc["cues"][0]["text"]="castor oil"
        doc["caption_corrections_snapshot"]=[correction]
        self.assertEqual(corrected_document(doc,[correction])["cues"][0]["text"],"castor oil")

    def test_cut_changes_reset_timed_overrides_but_visual_changes_keep_them(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        p.clips[0].visual_preset="punch_in"
        self.assertTrue(matches(doc,p))
        p.clips.reverse()
        context={"_subtitle_document":doc}
        self.assertEqual(resolve_events(context,p,events()),events())
        self.assertIn("cut changed",context["subtitle_notice"])

    def test_short_delivery_uses_corrected_caption_prefix_without_repeating_or_extending(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        doc["cues"][0]["text"]="Castor oil"
        short=derive_duration_variant(p,4)
        output=resolve_events({"_subtitle_document":doc,"_subtitle_prefix_variant":True},short,[])
        self.assertEqual(output[0]["text"],"Castor oil")
        self.assertEqual(output[1]["end"],4)

    def test_invalid_times_duplicate_ids_and_filter_expressions_are_rejected(self):
        for changes in [dict(start=float('nan')), dict(end=.1), dict(position="arbitrary_filter")]:
            with self.assertRaises(ValidationError):
                SubtitleCue.model_validate(dict(id="cue", start=.1, end=1, text="word") | changes)
        cue=SubtitleCue(id="cue",start=.1,end=1,text="word").model_dump()
        with self.assertRaises(ValueError): validate_cues([cue,cue],3)
        with self.assertRaises(ValueError): validate_cues([{**cue,"end":4}],3)
        with self.assertRaises(ValidationError): SubtitleEdit(base_hash='a'*64,revision=0,cues=[],shell="anything")

    def test_global_timing_revision_shifts_saved_captions_without_losing_text(self):
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        doc["cues"][0]["text"]="Castor oil"
        p.caption_timing_offset_seconds=.2
        output=resolve_events({"_subtitle_document":doc},p,events())
        self.assertAlmostEqual(output[0]["start"],.3)
        self.assertEqual(output[0]["text"],"Castor oil")
        self.assertEqual(doc["cues"][0]["start"],.1)

    def test_saved_plan_loads_subtitle_document_without_model_inference(self):
        from app.worker import prepare_run_speech_precision
        p=plan(); doc=make_document(p.model_dump(mode="json"),events())
        database=MagicMock();database.__enter__.return_value=database
        database.execute.return_value.fetchone.return_value={"speech_precision_snapshot":{},"subtitle_document":doc}
        context={"assets":[]};run={"edit_plan_id":uuid4()}
        with patch('app.worker.connection',return_value=database),patch('app.speech_precision.prepare_context',side_effect=AssertionError('no analysis')):
            prepare_run_speech_precision(context,run)
        self.assertEqual(context["_subtitle_document"]["cues"],doc["cues"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_render_shows_corrected_caption_and_hides_the_other_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.mp4';output=root/'corrected.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=160x284:r=30:d=3',
                '-f','lavfi','-i','sine=frequency=440:duration=3:sample_rate=48000','-c:v','libx264','-c:a','aac',str(source)],
                check=True,capture_output=True,timeout=20)
            p=plan();p.clips=p.clips[:1]
            doc=make_document(p.model_dump(mode="json"),[dict(start=.2,end=2,text='wrong'),dict(start=2.2,end=2.9,text='hide me')])
            doc['cues'][0].update(text='Castor oil',position='upper');doc['cues'][1]['hidden']=True
            out=resolve_events({'_subtitle_document':doc},p,[])
            captions=root/'subtitles.ass';captions.write_text(render_ass(out,width=160,height=284))
            _render_video([(source,0,3)],p,captions,output,30,width=160,height=284)
            def brightness(at):
                raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(output),'-frames:v','1','-pix_fmt','gray','-f','rawvideo','-'],timeout=10)
                return sum(raw)/len(raw)
            self.assertGreater(brightness(1),.5)
            self.assertLess(brightness(2.6),.1)
            self.assertIn('Castor oil',render_webvtt(out));self.assertNotIn('hide me',render_webvtt(out))


class SubtitleDraftApiTests(unittest.TestCase):
    def setUp(self):
        self.row=row(); self.base=api.base_document(self.row)
        self.changed=deepcopy(self.base);self.changed["cues"][0]["text"]="Castor oil!"
        self.changed["base_hash"]=fingerprint(self.base)
        self.draft=dict(revision=1,document=self.changed,applied_run_id=None)
        self.db=MagicMock(); self.db.__enter__.return_value=self.db

    def test_get_is_read_only_and_restores_saved_draft(self):
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=self.draft):
            output=api.get_subtitles(self.row["job_id"],self.row["id"])
        self.assertEqual(output["cues"][0]["text"],"Castor oil!")
        self.assertEqual(output["baseline"][0]["text"],"Costa Royal!")
        self.assertTrue(output["saved"])
        self.db.execute.assert_not_called()

    def test_saving_never_queues_a_render_or_mutates_saved_edit(self):
        self.db.execute.return_value.fetchone.side_effect=[dict(id=self.row["job_id"]),self.draft]
        payload=SubtitleEdit(base_hash=fingerprint(self.base),revision=0,cues=self.changed["cues"])
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=None):
            api.save_subtitles(self.row["job_id"],self.row["id"],payload)
        queries=[c.args[0] for c in self.db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO subtitle_drafts" in q for q in queries))
        self.assertFalse(any("INSERT INTO edit_runs" in q or "UPDATE jobs" in q for q in queries))
        self.assertEqual(self.row["manifest"]["subtitle_events"][0]["text"],"Costa Royal!")

    def test_stale_tab_cannot_overwrite_a_newer_draft(self):
        payload=SubtitleEdit(base_hash=fingerprint(self.base),revision=0,cues=self.changed["cues"])
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=self.draft):
            with self.assertRaises(HTTPException) as failure: api.save_subtitles(self.row["job_id"],self.row["id"],payload)
        self.assertEqual(failure.exception.status_code,409)
        self.assertFalse(any("INSERT" in c.args[0] for c in self.db.execute.call_args_list))

    def test_apply_queues_same_plan_without_mutating_the_approved_version(self):
        created=dict(id=uuid4(),version=3)
        self.db.execute.return_value.fetchone.side_effect=[dict(id=self.row["job_id"]),dict(id=self.row["id"],version=2),dict(id=uuid4()),created]
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=self.draft),patch.object(api,"assert_job_capacity"):
            result=api.apply_subtitles(self.row["job_id"],self.row["id"],api.SubtitleApply(base_hash=fingerprint(self.base),revision=1))
        self.assertEqual(result,created)
        queries=[c.args[0] for c in self.db.execute.call_args_list]
        self.assertTrue(any("SELECT job_id,%s,schema_version,document" in q for q in queries))
        self.assertFalse(any("UPDATE edit_plans" in q or "UPDATE approvals" in q for q in queries))

    def test_repeat_apply_returns_the_same_run_instead_of_rendering_twice(self):
        created=dict(id=uuid4(),version=3)
        self.draft["applied_run_id"]=created["id"]
        self.db.execute.return_value.fetchone.side_effect=[dict(id=self.row["job_id"]),created]
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=self.draft):
            self.assertEqual(api.apply_subtitles(self.row["job_id"],self.row["id"],api.SubtitleApply(base_hash=fingerprint(self.base),revision=1)),created)
        self.assertFalse(any("INSERT" in c.args[0] for c in self.db.execute.call_args_list))

    def test_apply_refuses_to_replace_a_newer_story(self):
        self.db.execute.return_value.fetchone.side_effect=[dict(id=self.row["job_id"]),dict(id=uuid4(),version=3)]
        with patch.object(api,"connection",return_value=self.db),patch.object(api,"load_run",return_value=self.row),patch.object(api,"load_draft",return_value=self.draft):
            with self.assertRaises(HTTPException) as failure: api.apply_subtitles(self.row["job_id"],self.row["id"],api.SubtitleApply(base_hash=fingerprint(self.base),revision=1))
        self.assertEqual(failure.exception.status_code,409)

    def test_legacy_preview_uses_actual_rendered_subtitles_before_any_reconstruction(self):
        saved=row(); saved["manifest"]={"outputs":{"captions":"caption.ass"}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'caption.ass').write_text(render_ass(events()))
            with patch.object(api,"get_settings",return_value=SimpleNamespace(media_root=root)),patch('app.editor_context.build_editor_context',side_effect=AssertionError('must use saved ASS')):
                output=api.base_document(saved)
        self.assertEqual(output['cues'][0]['text'],'Costa Royal!')
