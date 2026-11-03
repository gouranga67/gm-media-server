import array
from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4
import wave

from fastapi import HTTPException
from pydantic import ValidationError
from app import editing, worker
from app.edit_plan import TalkingHeadEditPlan, document_sha256, validate_edit_plan
from app.finishing_tools import FinishingTools, clip_voice_cleanup_filter, voice_finishing_filter
from app.grounded_revision import revision_spec, resolve_revision, replay_resolution, measured_quiet
from app.schemas import RevisionCreate
from app.subtitle_document import make_document, remap_document, matches


def fixture():
    first, second = str(uuid4()), str(uuid4())
    words = [dict(start=.3, end=.6, text="This"), dict(start=.7, end=1.1, text="cream"), dict(start=1.2, end=1.5, text="works."),
        dict(start=4.5, end=4.8, text="Here"), dict(start=4.9, end=5.2, text="is"), dict(start=5.3, end=5.6, text="the"), dict(start=5.7, end=6.2, text="proof.")]
    assets = [dict(asset_id=first, _storage_key="source.wav", duration_seconds=7, has_video=True, has_audio=True, mime_type="video/mp4",
        transcript_segments=[dict(start=.3, end=6.2, text="This cream works. Here is the proof.", words=words)]),
        dict(asset_id=second, duration_seconds=3, has_video=True, has_audio=True, mime_type="video/mp4",
            transcript_segments=[dict(start=.4, end=2.1, text="A different thought.", words=[dict(start=.4+i*.5,end=.7+i*.5,text=w) for i,w in enumerate("A different thought.".split())])])]
    plan = TalkingHeadEditPlan(schema_version="1.5", recipe="talking_head", caption_style="clean_blue_v1", audio_preset="spoken_voice_v1",
        end_card="none", editorial_summary="Recorded statements.", clips=[dict(asset_id=first, source_in=0, source_out=7, crop="center_fill"),
            dict(asset_id=second,source_in=0,source_out=3,crop="center_fill")])
    context = dict(ready_for_editing=True, project=dict(name="Fixture",brief="Keep the recorded story.",privacy_mode="hybrid",ai_copy_allowed=False),
        job=dict(recipe="talking_head",edit_style="clean",music_mode="none",max_duration_seconds=60), assets=assets,music_library=[],creative_effect_library=[])
    return plan, context


class GroundedRevisionTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.context = fixture()
        self.doc = self.plan.model_dump(mode="json")
        self.assets = self.context["assets"]

    def resolve(self, note, **kwargs):
        return resolve_revision(self.doc, note, self.assets, **kwargs)

    def test_only_whole_single_supported_commands_are_routed(self):
        for note in ['Make "cream works" louder by 3 dB','Please boost “cream works” in clip 1.', "Turn down 'cream works' by 2dB"]:
            self.assertEqual(revision_spec(note)["kind"], "phrase_audio")
        self.assertEqual(revision_spec('Shorten the pause after "cream works" to .5 seconds')["pause_seconds"], .5)
        self.assertEqual(revision_spec('MAKE "cream works" QUIETER BY 2 DB')["delta_db"], -2)
        for note in ['Make "cream works" louder and change the ending', 'Make it better', 'Make "cream works" sarcastic', 'Shorten the entire video', 'Turn down "cream works" louder']:
            self.assertIsNone(revision_spec(note))

    def test_phrase_audio_is_exact_local_and_preserves_media_and_other_regions(self):
        self.doc["finishing"] = FinishingTools(audio_regions=[dict(start=.5,end=1,gain_db=2),dict(start=8,end=9,gain_db=-2)]).model_dump(mode="json")
        original = deepcopy(self.doc)
        result = self.resolve('Make "cream works" louder by 3 dB')
        self.assertEqual(result["execution"]["target"]["start_seconds"], .7)
        self.assertEqual(result["execution"]["target"]["end_seconds"], 1.5)
        self.assertEqual(result["document"]["clips"], original["clips"])
        self.assertEqual(result["document"]["finishing"]["audio_regions"], [dict(start=.5,end=.7,gain_db=2),dict(start=.7,end=1,gain_db=5),
            dict(start=1,end=1.5,gain_db=3),dict(start=8,end=9,gain_db=-2)])
        self.assertEqual(result["execution"]["additional_model_calls"], 0)
        self.assertEqual(self.doc, original)
        validate_edit_plan(result["document"], self.assets)

    def test_case_punctuation_and_typographic_quotes_are_supported_without_fuzzy_words(self):
        self.assertEqual(self.resolve('Make “CREAM works!” quieter by 2 dB')["execution"]["target"]["phrase"], "cream works.")
        with self.assertRaisesRegex(ValueError,"not found"):
            self.resolve('Make "cream worked" louder by 3 dB')

    def test_repeated_quotes_require_an_occurrence_and_report_locations(self):
        self.doc["clips"] = [self.doc["clips"][0], deepcopy(self.doc["clips"][0])]
        with self.assertRaisesRegex(ValueError,"clip 1 at 0.7s, clip 2 at 7.7s"):
            self.resolve('Make "cream works" louder by 3 dB')
        result = self.resolve('Make "cream works" louder by 3 dB in clip 2')
        self.assertEqual(result["execution"]["target"]["start_seconds"],7.7)

    def test_partial_words_silent_sources_and_missing_timings_are_not_targets(self):
        self.doc["clips"][0]["source_in"] = .9
        with self.assertRaisesRegex(ValueError,"not found"):
            self.resolve('Make "cream works" louder by 3 dB')
        self.doc["clips"][0]["source_in"] = 0
        self.assets[0]["transcript_segments"][0]["words"] = []
        with self.assertRaisesRegex(ValueError,"word-timed"):
            self.resolve('Make "cream works" louder by 3 dB')

    def test_existing_automation_limits_are_checked_before_rendering(self):
        self.doc["finishing"] = FinishingTools(audio_regions=[dict(start=0,end=3,gain_db=11)]).model_dump(mode="json")
        with self.assertRaisesRegex(ValueError,"combined volume"):
            self.resolve('Make "cream works" louder by 3 dB')

    def test_quiet_pause_shortens_only_verified_space_and_preserves_all_words(self):
        result = self.resolve('Shorten the pause after "cream works" to 0.5 seconds', quiet_probe=lambda *_:[[1.5,4.5]], locks=["spoken phrases","clip order"])
        self.assertEqual(result["execution"]["target"]["removed_seconds"],2.5)
        self.assertEqual(result["execution"]["target"]["retained_pause_seconds"],.5)
        self.assertEqual(len(result["document"]["clips"]),3)
        self.assertEqual(result["document"]["clips"][-1],self.doc["clips"][-1])
        validate_edit_plan(result["document"],self.assets)

    def test_non_quiet_reactions_are_kept_and_actual_retained_pause_is_reported(self):
        result = self.resolve('Shorten the pause after "cream works" to 0.5 seconds',quiet_probe=lambda *_:[[3,4.2]])
        self.assertGreater(result["execution"]["target"]["retained_pause_seconds"],.5)
        self.assertGreaterEqual(result["document"]["clips"][0]["source_out"],3)
        for quiet in ([],[[1.6,1.65]]):
            with self.assertRaisesRegex(ValueError,"safely removable"):
                self.resolve('Shorten the pause after "cream works"',quiet_probe=lambda *_:quiet)

    def test_uncertain_word_handles_and_independent_audio_joins_are_respected(self):
        for word in self.assets[0]["transcript_segments"][0]["words"]:
            word.update(timing_source="interpolated",probability=.3)
        self.assets[0]["speech_precision"] = {"version":"speech_precision_v1"}
        result = self.resolve('Shorten the pause after "cream works" to 0.3 seconds',quiet_probe=lambda *_:[[1.5,4.5]])
        self.assertGreaterEqual(result["execution"]["target"]["retained_pause_seconds"],.5)
        self.doc["finishing"] = FinishingTools(audio_joins=[dict(clip_index=0,lead_seconds=0,tail_seconds=.5)]).model_dump(mode="json")
        with self.assertRaisesRegex(ValueError,"independent audio"):
            self.resolve('Shorten the pause after "cream works"')
        with self.assertRaisesRegex(ValueError,"not found"):
            self.resolve('Make "A different" louder by 2 dB')  # First word is muted under the preceding tail.

    def test_replay_is_bound_to_immutable_base_and_never_repeats_measurement(self):
        result = self.resolve('Shorten the pause after "cream works"',quiet_probe=lambda *_:[[1.5,4.5]])
        with patch('app.grounded_revision.measured_quiet',side_effect=AssertionError("no second inspection")):
            doc, execution = replay_resolution(result,self.doc)
        self.assertEqual(doc,result["document"])
        self.assertEqual(execution["scope"],"phrase_pause")
        changed = deepcopy(self.doc);changed["clips"][0]["source_out"] -= .1
        with self.assertRaisesRegex(ValueError,"base plan"):
            replay_resolution(result,changed)
        result["document"]["clips"][0]["source_out"] -= .1
        with self.assertRaisesRegex(ValueError,"integrity"):
            replay_resolution(result,self.doc)

    def test_pause_retimes_saved_subtitle_text_hidden_cards_and_positions(self):
        doc = make_document(self.doc,[dict(start=.3,end=1.8,text="Original spelling",position="upper"),dict(start=2,end=3,text="Pause only"),
            dict(start=4.5,end=6.3,text="Keep this correction",position="middle")])
        doc["cues"][0]["text"] = "Corrected spelling"
        doc["cues"][2]["hidden"] = True
        original = deepcopy(doc)
        result = self.resolve('Shorten the pause after "cream works"',quiet_probe=lambda *_:[[1.5,4.5]])
        mapped = remap_document(doc,self.doc,result["document"],result["timeline_mapping"])
        self.assertTrue(matches(mapped,result["document"]))
        self.assertEqual(len(mapped["cues"]),2)
        self.assertEqual(mapped["cues"][0]["text"],"Corrected spelling")
        self.assertEqual(mapped["cues"][0]["position"],"upper")
        self.assertTrue(mapped["cues"][1]["hidden"])
        self.assertEqual(mapped["cues"][1]["text"],"Keep this correction")
        self.assertAlmostEqual(mapped["cues"][1]["start"],2)
        self.assertEqual(doc,original)

    def test_phrase_gain_keeps_saved_automatic_take_balance(self):
        self.doc["finishing"] = FinishingTools(voice_cleanup="auto",voice_cleanup_profiles=[dict(asset_id=self.assets[0]["asset_id"],status="measured",balance_gain_db=6)]).model_dump(mode="json")
        result = self.resolve('Make "cream works" louder by 3 dB')
        plan = TalkingHeadEditPlan.model_validate(result["document"])
        self.assertEqual(clip_voice_cleanup_filter(plan,0),"volume=6.0dB")
        self.assertEqual(plan.finishing.audio_regions[0].gain_db,3)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_real_probe_distinguishes_a_quiet_gap_from_a_tone(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = array.array('h',[round(.2*math.sin(2*math.pi*440*i/16000)*32767) if i/16000<1.5 or i/16000>=4.5 else 0 for i in range(112000)])
            with wave.open(str(root/'source.wav'),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(samples.tobytes())
            settings=SimpleNamespace(media_root=root)
            self.assertTrue(measured_quiet(self.assets[0],1.5,4.5,settings))
            self.assertFalse(measured_quiet(self.assets[0],.3,1.3,settings))

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_rendered_phrase_gain_changes_only_its_selected_audio_window(self):
        result = self.resolve('Make "cream works" louder by 6 dB')
        plan = TalkingHeadEditPlan.model_validate(result['document'])
        rendered = subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
            'sine=frequency=440:sample_rate=48000:duration=3','-af',voice_finishing_filter(plan),
            '-f','f32le','-acodec','pcm_f32le','-'],check=True,capture_output=True,timeout=5)
        samples=array.array('f');samples.frombytes(rendered.stdout)
        rms=lambda a,b:math.sqrt(sum(x*x for x in samples[int(a*48000):int(b*48000)]) / int((b-a)*48000))
        before,phrase,after=rms(.2,.5),rms(.9,1.2),rms(2,2.3)
        self.assertAlmostEqual(20*math.log10(phrase/before),6,delta=.1)
        self.assertAlmostEqual(20*math.log10(after/before),0,delta=.1)
        self.assertEqual(len(samples),3*48000)


class GroundedRevisionFlowTests(unittest.TestCase):
    def api(self, note, *, duplicate=False, base=1, pause=False, local_only=False):
        plan, context = fixture()
        if duplicate: plan.clips=[plan.clips[0],plan.clips[0].model_copy(deep=True)]
        prior=dict(id=uuid4(),version=1,edit_plan_id=uuid4(),caption_corrections=[],effects_enabled=None,broll_enabled=None)
        if local_only: context['project']['privacy_mode']='local_only'
        if pause:
            from app.duration_policy import duration_settings
            prior['duration_policy']=duration_settings(dict(duration_mode='follow_story',target_duration_seconds=30,max_duration_seconds=60))
        subtitles=make_document(plan.model_dump(mode='json'),[dict(start=4.5,end=6.3,text='A saved correction',position='upper')]) if pause else None
        database=Mock()
        def execute(sql,params=()):
            if "SELECT id FROM jobs" in sql: row={"id":uuid4()}
            elif "SELECT * FROM edit_runs" in sql: row=prior
            elif "SELECT document" in sql: row={"document":plan.model_dump(mode="json"),"speech_precision_snapshot":{},"subtitle_document":subtitles}
            elif "COALESCE(max(version)" in sql: row={"version":2}
            elif "INSERT INTO edit_runs" in sql: row={"id":uuid4(),"status":"pending","version":2}
            else: row=None
            return Mock(fetchone=lambda:row)
        database.execute.side_effect=execute
        @contextmanager
        def connection(): yield database
        with patch.multiple(editing,_context_or_http=Mock(return_value=context),connection=connection,assert_job_capacity=Mock()), \
            patch('app.grounded_revision.measured_quiet',return_value=[[1.5,4.5]]):
            try: result=editing._request_revision(uuid4(),RevisionCreate(note=note,base_version=base))
            except HTTPException as error: result=error
        return result,database,plan

    def test_api_freezes_unique_quote_before_queueing_and_rejects_ambiguity_without_insert(self):
        result,db,plan=self.api('Make "cream works" louder by 3 dB')
        self.assertEqual(result["status"],"pending")
        params=next(c.args[1] for c in db.execute.call_args_list if 'INSERT INTO edit_runs' in c.args[0])
        frozen=params[-1].obj
        self.assertEqual(frozen['base_plan_sha256'],document_sha256(plan.model_dump(mode='json')))
        self.assertEqual(frozen['execution']['scope'],'phrase_audio')
        for options in (dict(duplicate=True),dict(base=None),dict(base=9)):
            error,db,_=self.api('Make "cream works" louder by 3 dB',**options)
            self.assertIsInstance(error,HTTPException)
            self.assertIn(error.status_code,(409,422))
            self.assertFalse(any('INSERT INTO edit_runs' in c.args[0] for c in db.execute.call_args_list))
        with self.assertRaises(ValidationError):
            RevisionCreate(note='Make "cream works" louder',base_version=1,finishing_settings=FinishingTools())

    def test_pause_preflight_freezes_retimed_custom_captions_and_parent_duration(self):
        result,db,_=self.api('Shorten the pause after "cream works" to .5 seconds',pause=True,local_only=True)
        self.assertEqual(result['status'],'pending')
        params=next(c.args[1] for c in db.execute.call_args_list if 'INSERT INTO edit_runs' in c.args[0])
        self.assertEqual(params[-2].obj['duration_mode'],'follow_story')
        frozen=params[-1].obj
        self.assertEqual(frozen['subtitle_document']['cues'][0]['text'],'A saved correction')
        self.assertAlmostEqual(frozen['subtitle_document']['cues'][0]['start'],2)
        self.assertEqual(frozen['execution']['scope'],'phrase_pause')

    def test_local_only_accepts_supported_quote_and_rejects_hosted_story_note(self):
        result,_,_=self.api('Make "cream works" louder',local_only=True)
        self.assertEqual(result['status'],'pending')
        result,db,_=self.api('Make the story more exciting',local_only=True)
        self.assertIsInstance(result,HTTPException)
        self.assertEqual(result.status_code,409)
        self.assertFalse(any('INSERT INTO edit_runs' in c.args[0] for c in db.execute.call_args_list))

    def test_invalid_local_document_never_uses_hosted_repair_or_renders(self):
        plan,context=fixture();document=plan.model_dump(mode='json')
        note='Make "cream works" louder'
        frozen=resolve_revision(document,note,context['assets'])
        run=dict(id=str(uuid4()),job_id=str(uuid4()),version=2,edit_plan_id=None,based_on_run_id=str(uuid4()),revision_note=note,revision_resolution=frozen)
        db=MagicMock();db.__enter__.return_value=db
        db.execute.return_value.fetchone.return_value=dict(version=1,document=document,caption_corrections=[])
        editor,renderer=Mock(),Mock()
        with patch.multiple(worker,claim_pending_edit=Mock(return_value=run),build_editor_context=Mock(return_value=context),connection=Mock(return_value=db),
            create_edit_plan=editor,render_edit_preview=renderer,validate_edit_plan=Mock(side_effect=ValueError('invalid saved local document'))):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        editor.assert_not_called();renderer.assert_not_called()
        self.assertTrue(any('failed' in str(c) and 'invalid saved local document' in str(c) for c in db.execute.call_args_list))

    def test_worker_replays_frozen_local_change_without_model_or_audio_reinspection(self):
        plan,context=fixture();document=plan.model_dump(mode='json')
        note='Make "cream works" louder by 3 dB'
        frozen=resolve_revision(document,note,context['assets'])
        run=dict(id=str(uuid4()),job_id=str(uuid4()),version=2,edit_plan_id=None,based_on_run_id=str(uuid4()),revision_note=note,revision_resolution=frozen)
        for resumed in (False,True):
            with self.subTest(resumed=resumed):
                current_run=deepcopy(run)
                if resumed: current_run['edit_plan_id']=str(uuid4())
                db=MagicMock();db.__enter__.return_value=db
                def execute(sql,params=()):
                    row=dict(version=1,document=document,caption_corrections=[])
                    if 'SELECT document, provider, model' in sql:
                        row=dict(document=frozen['document'],provider='local_revision_instruction',model='deterministic_editor_v1')
                    return Mock(fetchone=lambda:row)
                db.execute.side_effect=execute
                renderer=Mock(return_value=dict(outputs=dict(preview='preview.mp4'),manifest_path='manifest.json'))
                with patch.multiple(worker,claim_pending_edit=Mock(return_value=current_run),build_editor_context=Mock(return_value=deepcopy(context)),connection=Mock(return_value=db),
                    create_edit_plan=Mock(side_effect=AssertionError('no hosted editor')), _record_plan_usage=Mock(),_persist_generated_plan=Mock(),render_edit_preview=renderer), \
                    patch('app.audio_cleanup.prepare_voice_cleanup',side_effect=AssertionError('preserve saved audio decisions')):
                    self.assertTrue(worker.process_one_edit(worker.WorkerState()))
                renderer.assert_called_once()
                current,rendered=renderer.call_args.args[:2]
                self.assertEqual(rendered.clips,plan.clips)
                self.assertEqual(current['revision_report']['execution']['target']['phrase'],'cream works.')
                self.assertTrue(current['revision_report']['changed'])
