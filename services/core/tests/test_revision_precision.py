import unittest
from copy import deepcopy
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app import worker
from app.edit_plan import TalkingHeadEditPlan, validate_edit_plan
from app.revision_intent import assert_revision_locks, local_revision
from app.revision_report import compare_revision


def fixture():
    identity = str(uuid4())
    plan = TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head", caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1", end_card="none", editorial_summary="A complete recorded story.",
        clips=[dict(asset_id=identity, source_in=1, source_out=4, crop="center_fill"),
               dict(asset_id=identity, source_in=5, source_out=8, crop="center_fill")])
    asset = dict(asset_id=identity, duration_seconds=12, has_video=True, has_audio=True, mime_type="video/mp4",
        transcript_segments=[dict(start=1.2, end=3.5, text="A complete first thought.",
            words=[dict(start=1.2+n*0.5, end=1.5+n*0.5, text=text) for n,text in enumerate("A complete first thought.".split())])])
    return plan, asset


class RevisionPrecisionTests(unittest.TestCase):
    def test_local_volume_changes_only_requested_clip_and_preserves_source(self):
        plan, asset = fixture()
        original = plan.model_dump(mode="json")
        changed, execution = local_revision(original, "Please make clip 2 louder by 6 dB.")
        self.assertEqual(execution["additional_model_calls"], 0)
        self.assertEqual(changed["clips"][1]["source_audio_gain_db"], 6)
        expected = deepcopy(original)
        expected["clips"][1]["source_audio_gain_db"] = 6
        self.assertEqual(changed, expected)
        self.assertEqual(original, plan.model_dump(mode="json"))
        validate_edit_plan(changed, [asset])

    def test_only_complete_unambiguous_commands_take_local_lane(self):
        plan, _ = fixture()
        document = plan.model_dump(mode="json")
        for text in ("Make clip 2 louder by 6 dB and remove the ending", "Make it better", "Move captions to the top except the intro", "Make the funny line louder", "Set music to present"):
            self.assertIsNone(local_revision(document, text), text)
        for text in ("Make clip 99 louder by 6 dB", "Make clip 2 louder by 30 dB"):
            with self.assertRaises(ValueError):
                local_revision(document, text)

    def test_caption_music_and_removal_commands_preserve_other_choices(self):
        plan, _ = fixture()
        document = plan.model_dump(mode="json")
        document.update(music_track_id=str(uuid4()), music_mix="present", broll=[{"fixture": "cutaway"}],
            effects=[{"fixture": "effect"}], finishing={"callouts": [{"fixture": "callout"}], "voice_denoise": True})
        caption, _ = local_revision(document, "Move captions to the top")
        self.assertEqual(caption["caption_position"], "upper")
        self.assertEqual(caption["clips"], document["clips"])
        # Music remains governed by the saved job preference. Changing only
        # the plan here would disagree with preview/final validation.
        self.assertIsNone(local_revision(document, "Set music to subtle"))
        effects, _ = local_revision(document, "Remove effects")
        self.assertEqual(effects["effects"], [])
        self.assertNotIn("callouts", effects["finishing"])
        self.assertTrue(effects["finishing"]["voice_denoise"])
        self.assertEqual(effects["broll"], document["broll"])
        with self.assertRaisesRegex(ValueError, "protected"):
            local_revision(document, "Move captions to the top", ["captions"])

    def test_local_caption_position_moves_visible_regions_but_keeps_hidden_cues(self):
        plan, _ = fixture()
        document=plan.model_dump(mode="json")
        document["finishing"]={"caption_regions":[{"start":0,"end":2,"position":"middle"},
            {"start":2,"end":3,"position":"hidden"}]}
        changed,_=local_revision(document,"Move captions to the top")
        self.assertEqual([r["position"] for r in changed["finishing"]["caption_regions"]],["upper","hidden"])
        self.assertEqual(document["finishing"]["caption_regions"][0]["position"],"middle")

    def test_server_rejects_violating_user_locks_but_allows_trimmed_order(self):
        plan, asset = fixture()
        document = plan.model_dump(mode="json")
        changed = deepcopy(document)
        changed["caption_position"] = "upper"
        with self.assertRaisesRegex(ValueError, "protected captions"):
            validate_edit_plan(changed, [asset], creative_direction={"_revision_protection": {"previous": document, "locks": ["captions"]}})
        changed = deepcopy(document)
        changed["clips"].reverse()
        with self.assertRaisesRegex(ValueError, "clip order"):
            assert_revision_locks(changed, document, ["clip order"], [asset])
        changed = deepcopy(document)
        changed["clips"][0]["source_in"] = 1.1
        assert_revision_locks(changed, document, ["clip order", "spoken phrases"], [asset])
        changed["clips"][0]["source_in"] = 2
        with self.assertRaisesRegex(ValueError, "spoken phrases"):
            assert_revision_locks(changed, document, ["spoken phrases"], [asset])

    def test_missing_word_times_cannot_prove_changed_speech_is_identical(self):
        plan, asset = fixture()
        document = plan.model_dump(mode="json")
        changed = deepcopy(document)
        changed["clips"][0]["source_in"] = 1.1
        asset["transcript_segments"] = []
        with self.assertRaisesRegex(ValueError, "spoken phrases"):
            assert_revision_locks(changed, document, ["spoken phrases"], [asset])

    def test_partial_word_evidence_does_not_allow_unverified_speech_changes(self):
        plan,asset=fixture()
        document=plan.model_dump(mode="json")
        changed=deepcopy(document)
        changed["clips"][0]["source_out"]=3.9
        asset["transcript_segments"].append({"start":3.5,"end":4,"text":"Unaligned ending.","words":[]})
        with self.assertRaisesRegex(ValueError,"spoken phrases"):
            assert_revision_locks(changed,document,["spoken phrases"],[asset])

    def test_music_and_effect_locks_also_cover_finishing_tools_and_validation_changes(self):
        plan, asset = fixture()
        document = plan.model_dump(mode="json")
        document.update(music_track_id=str(uuid4()), music_mix="subtle")
        # The input matches the old plan, but the job's voice-only policy
        # normalizes music away. Check the final validated output too.
        with self.assertRaisesRegex(ValueError, "protected music"):
            validate_edit_plan(document, [asset], creative_direction={"music_mode":"none",
                "_revision_protection":{"previous":document,"locks":["music"]}})
        changed = deepcopy(document)
        changed["finishing"] = {"pointers":[{"fixture":"new visual"}]}
        with self.assertRaisesRegex(ValueError, "protected effects"):
            assert_revision_locks(changed, document, ["effects"], [asset])

    def test_private_lock_reference_is_not_duplicated_into_model_context(self):
        from app.editor_provider import _public_context
        plan, asset = fixture()
        context = {"job":{"_revision_protection":{"previous":plan.model_dump(mode="json"),"locks":["captions"]}},
            "assets":[asset]}
        self.assertNotIn("_revision_protection", _public_context(context, 120_000)["job"])

    def test_report_distinguishes_render_changes_from_post_copy(self):
        plan, _ = fixture()
        document = plan.model_dump(mode="json")
        report = compare_revision(document, {**document, "post_copy": "New posting caption"})
        self.assertFalse(report["changed"])
        self.assertTrue(report["post_copy_changed"])
        report = compare_revision(document, {**document, "caption_style": "clean_white_v1"})
        self.assertTrue(report["changed"])
        self.assertFalse(report["source_selection_changed"])

    def test_worker_uses_local_note_without_model_and_overrides_inherited_caption_position(self):
        plan, asset = fixture()
        document = plan.model_dump(mode="json")
        for note in ("Make clip 2 louder by 6 dB", "Move captions to the top"):
            with self.subTest(note=note):
                run = dict(id=str(uuid4()), job_id=str(uuid4()), version=2, edit_plan_id=None,
                    based_on_run_id=str(uuid4()), revision_note=note,
                    caption_settings={"position": "middle", "timing_offset_seconds": 0})
                context = dict(ready_for_editing=True, project=dict(name="Fixture", brief="A complete story.",privacy_mode="hybrid",ai_copy_allowed=False),
                    job=dict(recipe="talking_head",edit_style="clean"), assets=[asset], music_library=[], creative_effect_library=[])
                database = MagicMock()
                database.__enter__.return_value = database
                database.execute.return_value.fetchone.return_value = {"version":1, "document":document,"caption_corrections":[]}
                planner, budget, persist = Mock(), Mock(), Mock()
                renderer = Mock(return_value={"outputs":{"preview":"fixture.mp4"},"manifest_path":"fixture.json"})
                with patch.multiple(worker, claim_pending_edit=Mock(return_value=run), build_editor_context=Mock(return_value=context),
                    connection=Mock(return_value=database), create_edit_plan=planner, assert_ai_budget=budget,
                    _persist_generated_plan=persist, render_edit_preview=renderer):
                    self.assertTrue(worker.process_one_edit(worker.WorkerState()))
                planner.assert_not_called()
                budget.assert_not_called()
                renderer.assert_called_once()
                actual = renderer.call_args.args[1]
                if note.startswith("Move"):
                    self.assertEqual(actual.caption_position, "upper")
                    self.assertEqual(run["caption_settings"]["position"], "upper")
                else:
                    self.assertEqual(actual.clips[1].source_audio_gain_db, 6)
                self.assertEqual(context["revision_report"]["execution"]["route"], "local")
                self.assertFalse(context["revision_report"]["source_selection_changed"])
                self.assertEqual([(c.source_in,c.source_out) for c in actual.clips], [(1,4),(5,8)])

    def test_worker_remembers_removals_and_reports_a_model_noop_without_another_request(self):
        plan, asset = fixture()
        for note in ("Remove effects", "Remove B-roll", "Make the explanation clearer"):
            with self.subTest(note=note):
                run = dict(id=str(uuid4()),job_id=str(uuid4()),version=2,edit_plan_id=None,
                    based_on_run_id=str(uuid4()),revision_note=note)
                context = dict(ready_for_editing=True,project=dict(name="Fixture",brief="Explain the recording.",
                    privacy_mode="transcript_only",ai_copy_allowed=False),job=dict(recipe="talking_head",edit_style="clean"),
                    assets=[asset],music_library=[],creative_effect_library=[])
                database = MagicMock()
                database.__enter__.return_value=database
                database.execute.return_value.fetchone.return_value={"version":1,"document":plan.model_dump(mode="json"),"caption_corrections":[]}
                planner=Mock(return_value=(plan,{"provider":"chatgpt_plan","model":"fixture"}))
                budget=Mock()
                renderer=Mock(return_value={"outputs":{"preview":"fixture.mp4"},"manifest_path":"fixture.json"})
                with patch.multiple(worker,claim_pending_edit=Mock(return_value=run),build_editor_context=Mock(return_value=context),
                    connection=Mock(return_value=database),create_edit_plan=planner,assert_ai_budget=budget,
                    _persist_generated_plan=Mock(),render_edit_preview=renderer):
                    worker.process_one_edit(worker.WorkerState())
                renderer.assert_called_once()
                if note.startswith("Remove"):
                    planner.assert_not_called()
                    budget.assert_not_called()
                    key="effects_enabled" if note.endswith("effects") else "broll_enabled"
                    self.assertIs(run[key],False)
                    self.assertTrue(any("UPDATE edit_runs SET broll_enabled=CASE" in c.args[0] for c in database.execute.call_args_list))
                else:
                    planner.assert_called_once()
                    budget.assert_called_once()
                    self.assertFalse(context["revision_report"]["changed"])
                    self.assertIn("same cut",context["revision_report"]["notice"])
                    self.assertEqual(context["revision_report"]["execution"]["route"],"model")

    def test_later_revision_inherits_removals_unless_user_explicitly_reenables(self):
        from app import editing
        from app.schemas import RevisionCreate
        from contextlib import contextmanager
        prior=dict(id=uuid4(),version=1,caption_corrections=[],effects_enabled=False,broll_enabled=False)
        context=dict(ready_for_editing=True,assets=[],project={"privacy_mode":"transcript_only"})
        for override in (None,True):
            with self.subTest(override=override):
                database=Mock()
                def query(sql, params=()):
                    if "SELECT id FROM jobs" in sql:
                        row={"id":uuid4()}
                    elif "SELECT * FROM edit_runs" in sql:
                        row=prior
                    elif "COALESCE(max(version)" in sql:
                        row={"version":2}
                    elif "INSERT INTO edit_runs" in sql:
                        row={"id":uuid4(),"version":2,"status":"pending"}
                    else:
                        row=None
                    return Mock(fetchone=lambda:row)
                database.execute.side_effect=query
                @contextmanager
                def connection():
                    yield database
                payload=RevisionCreate(note="Clarify the explanation",base_version=1,effects_enabled=override,broll_enabled=override)
                with patch.multiple(editing,_context_or_http=Mock(return_value=context),connection=connection,assert_job_capacity=Mock()):
                    editing._request_revision(uuid4(),payload)
                values=next(c.args[1] for c in database.execute.call_args_list if "INSERT INTO edit_runs" in c.args[0])
                self.assertIs(values[6],False if override is None else True)
                self.assertIs(values[10],False if override is None else True)
