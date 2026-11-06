import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app import worker
from app.edit_plan import TalkingHeadEditPlan
from app.take_quality import editing_policy


class StoryQualityWorkerTests(unittest.TestCase):
    def test_selected_story_uses_existing_bounded_repair_if_ending_is_missing(self):
        from app.story_contract import contract_for
        asset_id, job_id = str(uuid4()), str(uuid4())
        script=[{"evidence_id":i+1,"asset_id":asset_id,"start":start,"end":end,"text":text,"role":role}
                for i,(start,end,text,role) in enumerate([(0,2,"A complete opening.","hook"),(4,6,"Its real explanation.","development"),(8,10,"The recorded ending.","ending")])]
        context={"ready_for_editing":True,"project":{"name":"A story","brief":"Use the selected story.","privacy_mode":"hybrid","ai_copy_allowed":False},
                 "job":{"recipe":"talking_head","edit_style":"clean","editorial_policy":{"intent":"story"}},
                 "assets":[{"asset_id":asset_id,"duration_seconds":12,"has_video":True,"has_audio":True}],
                 "music_library":[],"creative_effect_library":[],
                 "selected_concept":{"script":script,"story_contract":contract_for("A clear explanation and result.",script),"reel_kind":"story"}}
        run={"id":str(uuid4()),"job_id":job_id,"version":1,"edit_plan_id":None,"based_on_run_id":None}
        bad=TalkingHeadEditPlan(schema_version="1.4",recipe="talking_head",clips=[{"asset_id":asset_id,"source_in":0,"source_out":2,"crop":"center_fill"}],caption_style="clean_blue_v1",audio_preset="spoken_voice_v1",end_card="none",editorial_summary="Forgot the ending.")
        good=bad.model_copy(update={"clips":[bad.clips[0].model_copy(update={"source_in":a,"source_out":b}) for a,b in [(0,2),(4,6),(8,10)]]},deep=True)
        planner=Mock(side_effect=[(bad,{"provider":"chatgpt_plan","model":"test"}),(good,{"provider":"chatgpt_plan","model":"test"})])
        renderer=Mock(return_value={"outputs":{"preview":"preview.mp4"},"manifest_path":"manifest.json"})
        with patch.multiple(worker,claim_pending_edit=Mock(return_value=run),build_editor_context=Mock(return_value=context),create_edit_plan=planner,assert_ai_budget=Mock(),_record_plan_usage=Mock(),_persist_generated_plan=Mock(),render_edit_preview=renderer,connection=MagicMock()):
            worker.process_one_edit(worker.WorkerState())
        self.assertEqual(planner.call_count,2)
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.args[0]['story_contract_review']['status'],'checked')
        self.assertEqual(len(renderer.call_args.args[1].clips),3)

    def test_missing_transition_does_not_trigger_another_model_call(self):
        asset_id = str(uuid4())
        run = {"id": str(uuid4()), "job_id": str(uuid4()), "version": 1,
               "edit_plan_id": None, "based_on_run_id": None}
        context = {"ready_for_editing": True,
            "project": {"name": "Product ad", "brief": "Make an engaging ad", "privacy_mode": "hybrid", "ai_copy_allowed": False},
            "job": {"edit_style": "energetic"},
            "assets": [{"asset_id": asset_id, "duration_seconds": 30, "has_video": True, "has_audio": True}],
            "music_library": [], "creative_effect_library": []}
        proposed = TalkingHeadEditPlan(schema_version="1.3", recipe="talking_head",
            clips=[{"asset_id": asset_id, "source_in": 0, "source_out": 10, "crop": "center_fill", "visual_preset": "punch_in"},
                   {"asset_id": asset_id, "source_in": 12, "source_out": 24, "crop": "center_fill"}],
            caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none", editorial_summary="A complete story.")
        planner = Mock(return_value=(proposed, {"provider": "chatgpt_plan", "model": "test"}))
        renderer = Mock(return_value={"outputs": {"preview": "preview.mp4"}, "manifest_path": "manifest.json"})
        connection = MagicMock()
        with patch.multiple(worker, claim_pending_edit=Mock(return_value=run),
            build_editor_context=Mock(return_value=context), create_edit_plan=planner,
            assert_ai_budget=Mock(), _record_plan_usage=Mock(), _persist_generated_plan=Mock(),
            render_edit_preview=renderer, connection=connection):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_called_once()
        renderer.assert_called_once()
        plan = renderer.call_args.args[1]
        self.assertEqual([(c.source_in, c.source_out) for c in plan.clips], [(0, 10), (12, 24)])
        self.assertEqual(plan.clips[1].transition, "cut")
        queries = [call.args[0] for call in connection.return_value.__enter__.return_value.execute.call_args_list]
        self.assertFalse(any("status = 'failed'" in query for query in queries))

    def test_story_repair_pass_is_checked_and_rendered_before_marking_ready(self):
        asset_id = str(uuid4())
        run = {"id": str(uuid4()), "job_id": str(uuid4()), "version": 1,
               "edit_plan_id": None, "based_on_run_id": None}
        context = {"ready_for_editing": True,
            "project": {"name": "Product ad", "brief": "Funny and engaging", "privacy_mode": "hybrid", "ai_copy_allowed": False},
            "job": {"editorial_policy": editing_policy({"project_name": "Product ad"})},
            "assets": [{"asset_id": asset_id, "duration_seconds": 20, "has_video": True, "has_audio": True,
                        "transcript_segments": [{"start": 2, "end": 4, "text": "Not saying it again."}]}],
            "music_library": [], "creative_effect_library": []}
        bad = TalkingHeadEditPlan(schema_version="1.3", recipe="talking_head",
            clips=[{"asset_id": asset_id, "source_in": 0, "source_out": 8, "crop": "center_fill"}],
            caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none",
            editorial_summary="Wrongly chose a retake.")
        good = bad.model_copy(deep=True)
        good.clips[0].source_in, good.clips[0].source_out = 10, 14
        provenance = {"provider": "chatgpt_plan", "model": "test", "reasoning_effort": "medium"}
        planner = Mock(side_effect=[(bad, provenance), (good, provenance)])
        renderer = Mock(return_value={"outputs": {"preview": "preview.mp4"}, "manifest_path": "manifest.json"})
        connection = MagicMock()
        with patch.multiple(worker, claim_pending_edit=Mock(return_value=run),
            build_editor_context=Mock(return_value=context), create_edit_plan=planner,
            assert_ai_budget=Mock(), _record_plan_usage=Mock(), _persist_generated_plan=Mock(),
            render_edit_preview=renderer, connection=connection):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        self.assertEqual(planner.call_count, 2)
        self.assertIn("production/retake chatter", context["validation_correction"]["error"])
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.args[1].clips[0].source_in, 10)
        queries = [call.args[0] for call in connection.return_value.__enter__.return_value.execute.call_args_list]
        self.assertTrue(any("status = 'ready'" in query for query in queries))
        self.assertFalse(any("status = 'failed'" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
