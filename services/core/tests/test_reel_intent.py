import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from pydantic import ValidationError
from fastapi import HTTPException

from app.edit_plan import repair_predictable_plan_defaults, validate_edit_plan
from app.editor_provider import ProviderUnavailable, _model_content, _parse_sse_response
from app.learning import learning_context_for_job
from app.learning_lab import assert_holdout, propose_from_notes
from app.schemas import JobCreate
from app.story_intelligence import build_story_assessment, select_story_moments
from app.take_quality import editing_policy


class ReelIntentTests(unittest.TestCase):
    def test_explicit_purpose_wins_over_product_words_and_style(self):
        job = {"brief": "Outtakes from the soap ad", "project_name": "Product ad", "edit_style": "high_impact"}
        for purpose in ("auto", "bloopers"):
            policy = editing_policy({**job, "reel_intent": purpose})
            self.assertTrue(policy["bloopers_requested"])
            self.assertFalse(policy["promotional"])
        self.assertFalse(editing_policy({**job, "reel_intent": "story"})["promotional"])
        self.assertFalse(editing_policy({**job, "reel_intent": "promotion"})["bloopers_requested"])
        self.assertFalse(editing_policy({"brief": "Make an ad without bloopers"})["bloopers_requested"])
        self.assertFalse(editing_policy({"brief": "Funny ad", "effect_level": "meme_heavy"})["bloopers_requested"])
        self.assertEqual(JobCreate().reel_intent, "auto")
        with self.assertRaises(ValidationError):
            JobCreate(reel_intent="made_up")

    def test_outtake_prompt_has_no_conflicting_generic_story_or_clean_take_rules(self):
        for recipe in ("talking_head", "montage"):
            context = {
                "project": {"privacy_mode": "text_only", "brief": "Make a blooper reel from the ad"},
                "job": {"recipe": recipe, "edit_style": "high_impact", "reel_intent": "bloopers",
                        "editorial_policy": editing_policy({"reel_intent": "bloopers"})},
                "assets": [], "learning_preferences": {"directives": ["Always replace false starts with clean sales takes."]},
                "revision": {"instruction": "Keep the mistake", "mode": "rebuild_story", "previous_plan": {"clips": []}},
            }
            prompt = _model_content(context, SimpleNamespace(editor_max_context_characters=120_000))[0]["text"]
            self.assertIn("recorded stumble", prompt)
            self.assertIn("unresolved question", prompt)
            self.assertIn("No role quota or minimum duration", prompt)
            self.assertNotIn("Prefer a complete clean take", prompt)
            self.assertNotIn("cover its missing roles", prompt)
            self.assertNotIn("then give only the context", prompt)
            # Instructions are tested separately from the serialized context.
            self.assertNotIn("These preferences were learned locally", prompt)
            self.assertNotIn("Always replace false starts", prompt)
            self.assertNotIn("transition beat when the edit is at least 20 seconds", prompt)

    def test_outtakes_keep_restart_evidence_and_have_no_generic_coverage_score(self):
        moments = [
            {"kind": "spoken", "text": "Start that again.", "start_seconds": 0, "intrinsic_score": 0.02},
            {"kind": "spoken", "text": "A clean complete sales explanation.", "start_seconds": 4, "intrinsic_score": 0.8},
        ]
        selected = select_story_moments(moments, "", 1, preserve_outtakes=True)
        self.assertEqual(selected[0]["text"], "Start that again.")
        report = build_story_assessment(selected, editing_policy({"reel_intent": "bloopers"}))
        self.assertEqual(report["review_mode"], "outtake_review")
        self.assertEqual(report["coverage"], {})
        self.assertEqual(report["duplicate_idea_groups"], [])
        self.assertTrue(any("restart can be the joke" in text for text in report["recommendations"]))

    def test_high_impact_outtakes_do_not_require_a_transition_or_zoom(self):
        asset_id = str(uuid4())
        document = {"schema_version": "1.3", "recipe": "talking_head",
            "clips": [{"asset_id": asset_id, "source_in": 0, "source_out": 10, "crop": "center_fill", "visual_preset": "standard"},
                      {"asset_id": asset_id, "source_in": 10, "source_out": 22, "crop": "center_fill", "visual_preset": "standard"}],
            "caption_style": "clean_blue_v1", "audio_preset": "spoken_voice_v1", "end_card": "none",
            "editorial_summary": "A recorded outtake", "music_track_id": None, "music_mix": "none", "effects": []}
        direction = {"edit_style": "high_impact", "editorial_policy": editing_policy({"reel_intent": "bloopers"})}
        assets = [{"asset_id": asset_id, "has_video": True, "has_audio": True, "duration_seconds": 24}]
        repaired, repairs = repair_predictable_plan_defaults(document, creative_direction=direction, complete_creative_defaults=True)
        self.assertEqual(repaired, document)
        self.assertFalse(repairs)
        plan = validate_edit_plan(document, assets, creative_direction=direction, enforce_story_quality=True)
        self.assertEqual(plan.clips[-1].source_out, 22)
        with self.assertRaisesRegex(ValueError, "visual emphasis"):
            validate_edit_plan(document, assets, creative_direction={"edit_style": "high_impact"})

    def test_clean_take_learning_is_not_transferred_to_bloopers(self):
        database = Mock()
        database.execute.return_value.fetchone.return_value = {"enabled": True, "minimum_samples": 3}
        context = learning_context_for_job(database, {"recipe": "talking_head", "reel_intent": "bloopers"})
        self.assertEqual(context["directives"], [])
        self.assertEqual(database.execute.call_count, 1)
        rows = [{"id": str(uuid4()), "job_id": str(uuid4()), "recipe": "talking_head", "reel_intent": "bloopers",
                 "edit_style": "high_impact", "note": "The long pause was funny"} for _ in range(3)]
        self.assertEqual(propose_from_notes(rows), [])

    def test_provider_overload_is_explicit_and_does_not_retry_a_model_call(self):
        event = {"type": "response.failed", "response": {"error": {"code": "server_is_overloaded"}}}
        with self.assertRaisesRegex(ProviderUnavailable, "editor service is temporarily busy"):
            _parse_sse_response([("data: " + json.dumps(event)).encode()])

    def test_clean_take_lesson_trial_cannot_override_a_blooper_job(self):
        database = Mock()
        database.execute.return_value.fetchone.return_value = {
            "recipe": "talking_head", "edit_style": "high_impact", "reel_intent": "bloopers"}
        lesson = {"training_job_ids": [], "training_source_hashes": [], "recipe": "talking_head", "edit_style": "high_impact"}
        with patch("app.learning_lab.source_hashes", return_value=[]):
            with self.assertRaisesRegex(HTTPException, "clean-take lessons do not apply"):
                assert_holdout(database, lesson, uuid4())


if __name__ == "__main__":
    unittest.main()
