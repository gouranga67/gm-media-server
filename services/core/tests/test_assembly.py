import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from psycopg.errors import UniqueViolation
from pydantic import ValidationError

from app.assembly import (
    AssemblySettings,
    decide_assembly,
    persist_assembly,
    preview_assembly,
    update_assembly,
)
from app.brief_direction import read_brief
from app import worker
from app.edit_plan import MontageEditPlan, validate_edit_plan
from app.editor_provider import _model_content
from app.projects import create_job
from app.schemas import JobCreate
from app.take_quality import editing_policy


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            "id": str(uuid4()),
            "recipe": "talking_head",
            "assembly_mode": "auto",
            "pacing_mode": "auto",
            "edit_style": "energetic",
            "reel_intent": "auto",
            "brief": "Make a story.",
        }
        self.voice = {
            "asset_id": str(uuid4()),
            "has_video": True,
            "has_audio": True,
            "duration_seconds": 20,
            "transcript_segments": [
                {"start": 1, "end": 8, "text": "A complete recorded explanation."}
            ],
        }
        self.picture = {"asset_id": str(uuid4()), "mime_type": "image/png"}
        self.quiet = {
            "asset_id": str(uuid4()),
            "has_video": True,
            "has_audio": False,
            "duration_seconds": 8,
        }
        self.assets = [self.voice, self.quiet, self.picture]

    def decide(self, brief, assets=None, **settings):
        return decide_assembly(
            {**self.job, "brief": brief, **settings},
            self.assets if assets is None else assets,
        )

    def test_mixed_explanation_keeps_speech_despite_montage_word(self):
        for brief in [
            "Use montage-style cutaways, but keep my whole explanation.",
            "Do not make a montage. Keep my speech.",
            "Make a gentle feel-good product montage; keep the spoken explanation.",
        ]:
            with self.subTest(brief=brief):
                decision = self.decide(brief)
                self.assertEqual(decision["recipe"], "talking_head")
                self.assertEqual(decision["hosted_model_calls"], 0)
        self.assertEqual(self.decide(brief)["edit_style"], "calm")

    def test_visual_montage_photos_and_silent_video(self):
        decision = self.decide(
            "A slow, feel-good music-led montage.", [self.quiet, self.picture]
        )
        self.assertEqual(
            (decision["recipe"], decision["edit_style"], decision["purpose"]),
            ("montage", "calm", "story"),
        )
        self.assertEqual(
            self.decide("A music-led visual montage.")["recipe"], "montage"
        )

    def test_product_sources_and_old_project_titles_do_not_request_an_ad(self):
        direction = {
            **self.job,
            "brief": "Do not make an ad. Explain it calmly.",
            "project_name": "Product ad",
        }
        self.assertEqual(decide_assembly(direction, self.assets)["purpose"], "story")
        self.assertFalse(editing_policy(direction)["promotional"])
        self.assertEqual(self.decide("Explain these products.")["purpose"], "story")
        self.assertEqual(
            self.decide("Make an ad for the product.")["purpose"], "promotion"
        )
        self.assertEqual(
            self.decide("No bloopers. Make an ad.")["purpose"], "promotion"
        )

    def test_negated_outtakes_and_source_metadata_cannot_request_bloopers(self):
        self.voice.update(source_name="bloopers.mp4", library_notes="Make an ad")
        self.assertEqual(
            self.decide("No bloopers. Make a clean explanation.")["purpose"], "story"
        )
        self.assertEqual(
            self.decide("A funny energetic story.", effect_level="meme_heavy")[
                "purpose"
            ],
            "story",
        )
        self.assertEqual(
            read_brief({"brief": "Do not use fast-paced cuts; use gentle pacing."})[
                "style"
            ],
            "calm",
        )

    def test_bloopers_have_speech_path_and_outtake_policy(self):
        decision = self.decide(
            "Make a bloopers reel with the actual stumble and real reaction."
        )
        self.assertEqual(
            (decision["recipe"], decision["purpose"]), ("talking_head", "bloopers")
        )
        policy = editing_policy({**self.job, "brief": "Make bloopers, not an ad."})
        self.assertTrue(policy["bloopers_requested"])
        self.assertFalse(policy["promotional"])

    def test_missing_speech_does_not_turn_a_blooper_request_into_a_silent_montage(self):
        with self.assertRaisesRegex(ValueError, "recorded.*speech"):
            self.decide("Make recorded bloopers.", [self.quiet, self.picture])

    def test_advanced_conflicts_are_reported_before_planning(self):
        with self.assertRaisesRegex(ValueError, "purpose conflicts"):
            self.decide("Make bloopers.", reel_intent="promotion")
        with self.assertRaisesRegex(ValueError, "gentle pacing"):
            self.decide(
                "A gentle explanation.", pacing_mode="manual", edit_style="high_impact"
            )
        with self.assertRaisesRegex(ValueError, "explicit style is calm"):
            self.decide(
                "Make a high-impact reel.", pacing_mode="manual", edit_style="calm"
            )
        self.assertEqual(
            self.decide("An explanation.", assembly_mode="montage")["recipe"], "montage"
        )

    def test_follow_brief_can_resolve_profile_pacing_but_retains_original_request(self):
        result = self.decide("A warm, unhurried explanation.", edit_style="high_impact")
        self.assertEqual(result["edit_style"], "calm")
        self.assertEqual(result["requested_edit_style"], "high_impact")
        self.assertEqual(
            self.decide("An explanation.", edit_style="high_impact")["edit_style"],
            "high_impact",
        )

    def test_broll_labelled_speaking_take_is_not_a_dialogue_spine(self):
        assets = [{**self.voice, "library_role": "broll"}, self.picture]
        self.assertEqual(
            self.decide("Make a visual sequence.", assets)["recipe"], "montage"
        )
        with self.assertRaisesRegex(ValueError, "recorded video speech"):
            self.decide("Keep my speech.", assets)

    def test_unsupported_inputs_are_explicit_and_not_filled_with_duplicates(self):
        for assets, message in [
            ([self.picture], "single still"),
            ([], "Add a video or photo"),
            ([{"has_audio": True}], "Audio-only"),
            (
                [
                    self.picture,
                    {"has_audio": True, "transcript_segments": [{"text": "Narration"}]},
                ],
                "audio-file narration",
            ),
        ]:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                self.decide("Make an edit.", assets)

    def test_preflight_is_read_only_waits_for_analysis_and_preserves_input(self):
        context = {
            "job": self.job,
            "project": {"brief": "Keep the explanation."},
            "assets": self.assets,
            "ready_for_editing": False,
        }
        original = deepcopy(context)
        self.assertFalse(preview_assembly(context)["ready"])
        context["ready_for_editing"] = True
        before = deepcopy(context)
        self.assertTrue(preview_assembly(context)["ready"])
        self.assertEqual(context, before)
        context["ready_for_editing"] = original["ready_for_editing"]
        self.assertEqual(context, original)

    def test_persistence_is_once_and_sticky_for_retry(self):
        context = {
            "job": self.job,
            "project": {"brief": "Keep the explanation."},
            "assets": self.assets,
            "ready_for_editing": True,
        }
        database = MagicMock()
        database.execute.return_value.fetchone.return_value = self.job
        decision = persist_assembly(database, context)
        self.assertEqual(database.execute.call_count, 3)
        stored = {**self.job, "assembly_decision": decision}
        database.reset_mock()
        database.execute.return_value.fetchone.return_value = stored
        context["project"]["brief"] = "A visual montage."
        self.assertEqual(persist_assembly(database, context), decision)
        self.assertEqual(database.execute.call_count, 1)
        self.assertTrue(preview_assembly({**context, "job": stored})["locked"])

    def test_advanced_settings_cannot_change_any_existing_run_even_failed(self):
        database = MagicMock()
        database.execute.return_value.fetchone.side_effect = [
            {"id": self.job["id"]},
            {"status": "failed"},
        ]
        settings = AssemblySettings(
            assembly_mode="montage",
            pacing_mode="auto",
            edit_style="calm",
            reel_intent="auto",
        )
        with patch("app.assembly.connection") as connect:
            connect.return_value.__enter__.return_value = database
            with self.assertRaises(HTTPException) as raised:
                update_assembly(uuid4(), settings)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(
            any(
                "UPDATE jobs" in call.args[0]
                for call in database.execute.call_args_list
            )
        )

    def test_legacy_api_clients_keep_their_explicit_engine(self):
        for recipe in ["talking_head", "montage"]:
            payload = JobCreate(recipe=recipe)
            self.assertIsNone(payload.assembly_mode)
            self.assertEqual(payload.pacing_mode, "manual")
        with self.assertRaises(ValidationError):
            JobCreate(assembly_mode="another_engine")

    def test_replayed_create_is_idempotent_after_auto_resolution(self):
        project_id = uuid4()
        payload = JobCreate(id=uuid4(), assembly_mode="auto", pacing_mode="auto")
        stored = {
            **payload.model_dump(),
            "id": payload.id,
            "project_id": project_id,
            "recipe": "montage",
            "edit_style": "calm",
            "assembly_decision": {"requested_edit_style": "energetic"},
        }
        first, second = MagicMock(), MagicMock()
        first.execute.side_effect = UniqueViolation()
        second.execute.return_value.fetchone.return_value = stored
        with patch("app.projects.connection") as connect:
            connect.side_effect = [first, second]
            first.__enter__.return_value = first
            second.__enter__.return_value = second
            self.assertEqual(
                create_job(
                    project_id, payload, x_gm_user_login="editor@example.invalid"
                ),
                stored,
            )

    def test_calm_automatic_cutaway_preserves_dialogue_and_bounds(self):
        document = {
            "schema_version": "1.4",
            "recipe": "talking_head",
            "clips": [
                {
                    "asset_id": self.voice["asset_id"],
                    "source_in": 0,
                    "source_out": 10,
                    "crop": "center_fill",
                }
            ],
            "caption_style": "clean_blue_v1",
            "audio_preset": "spoken_voice_v1",
            "end_card": "none",
            "editorial_summary": "Complete explanation with supporting picture.",
            "broll": [
                {
                    "asset_id": self.picture["asset_id"],
                    "media_kind": "image",
                    "source_in": 0,
                    "source_out": 0,
                    "start_seconds": 3,
                    "duration_seconds": 2,
                    "editorial_intent": "Show the relevant review.",
                }
            ],
        }
        plan = validate_edit_plan(
            document, self.assets, creative_direction={**self.job, "edit_style": "calm"}
        )
        self.assertEqual(plan.clips[0].source_out, 10)
        self.assertEqual(len(plan.broll), 1)
        document["broll"][0]["start_seconds"] = 9
        with self.assertRaisesRegex(ValueError, "beyond"):
            validate_edit_plan(
                document,
                self.assets,
                creative_direction={**self.job, "edit_style": "calm"},
            )

    def test_calm_prompt_allows_cutaways_without_high_impact_quota_or_extra_images(
        self,
    ):
        context = {
            "job": {**self.job, "edit_style": "calm"},
            "project": {"privacy_mode": "text_only"},
            "assets": self.assets,
        }
        before = deepcopy(context)
        content = _model_content(
            context, SimpleNamespace(editor_max_context_characters=120000)
        )
        self.assertEqual(len(content), 1)
        self.assertIn("picture-only cutaways", content[0]["text"])
        self.assertNotIn("every 2–3 seconds", content[0]["text"])
        self.assertNotIn("enabled only by", content[0]["text"])
        self.assertEqual(context, before)

    def test_worker_resolves_concept_job_before_its_single_editor_request(self):
        run = {
            "id": str(uuid4()),
            "job_id": self.job["id"],
            "version": 1,
            "edit_plan_id": None,
            "based_on_run_id": None,
        }
        initial = {
            "job": self.job,
            "project": {
                "brief": "A calm visual montage.",
                "privacy_mode": "hybrid",
                "ai_copy_allowed": False,
            },
            "assets": [self.quiet, self.picture],
            "ready_for_editing": True,
            "music_library": [],
            "creative_effect_library": [],
        }
        decision = decide_assembly(
            {**self.job, "brief": initial["project"]["brief"]}, initial["assets"]
        )
        resolved = {
            **initial,
            "job": {
                **self.job,
                "recipe": "montage",
                "edit_style": "calm",
                "assembly_decision": decision,
            },
        }
        plan = MontageEditPlan(
            schema_version="1.4",
            recipe="montage",
            audio_preset="montage_mix_v1",
            end_card="none",
            editorial_summary="A gentle sequence.",
            clips=[
                {
                    "asset_id": self.quiet["asset_id"],
                    "media_kind": "video",
                    "source_in": 0,
                    "source_out": 2,
                    "duration": 2,
                    "crop": "center_fill",
                },
                {
                    "asset_id": self.picture["asset_id"],
                    "media_kind": "image",
                    "source_in": 0,
                    "source_out": 0,
                    "duration": 2,
                    "crop": "center_fill",
                },
            ],
        )
        planner = Mock(
            return_value=(plan, {"provider": "chatgpt_plan", "model": "fixture"})
        )
        render = Mock(
            return_value={
                "outputs": {"preview": "preview.mp4"},
                "manifest_path": "manifest.json",
            }
        )
        build = Mock(side_effect=[initial, resolved])
        with (
            patch("app.assembly.persist_assembly", return_value=decision) as persist,
            patch.multiple(
                worker,
                claim_pending_edit=Mock(return_value=run),
                build_editor_context=build,
                create_edit_plan=planner,
                assert_ai_budget=Mock(),
                _record_plan_usage=Mock(),
                _persist_generated_plan=Mock(),
                render_montage_preview=render,
                connection=MagicMock(),
            ),
        ):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        persist.assert_called_once()
        planner.assert_called_once_with(resolved)
        render.assert_called_once()
        self.assertEqual(render.call_args.args[1].recipe, "montage")

    def test_selected_concept_quotes_cannot_change_its_purpose_or_manual_pacing(self):
        context = {
            "job": {
                **self.job,
                "reel_intent": "story",
                "edit_style": "high_impact",
                "pacing_mode": "manual",
            },
            "project": {
                "brief": "Selected concept. context: Our gentle cream and bloopers from our last ad."
            },
            "assets": self.assets,
            "ready_for_editing": True,
            "selected_concept": {
                "reel_kind": "story",
                "script": [{"text": "Our gentle cream"}],
            },
        }
        result = preview_assembly(context)
        self.assertTrue(result["ready"], result["error"])
        self.assertEqual(result["decision"]["purpose"], "story")
        self.assertEqual(result["decision"]["recipe"], "talking_head")
        self.assertEqual(result["decision"]["edit_style"], "high_impact")

    def test_short_video_and_non_ready_frozen_jobs_remain_explicit(self):
        with self.assertRaisesRegex(ValueError, "longer video"):
            self.decide(
                "Make a visual montage.", [{**self.quiet, "duration_seconds": 0.7}]
            )
        context = {
            "job": {**self.job, "assembly_decision": {"recipe": "montage"}},
            "ready_for_editing": False,
        }
        result = preview_assembly(context)
        self.assertFalse(result["ready"])
        self.assertTrue(result["locked"])


if __name__ == "__main__":
    unittest.main()
