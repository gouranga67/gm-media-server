import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.editor_provider import _model_content
from app.learning import derive_learning_preferences
from app.schemas import EditFeedbackCreate, EditFeedbackResponse, LearningSettingsUpdate


class LearningLoopTests(unittest.TestCase):
    def test_waits_for_repeated_feedback_before_learning(self) -> None:
        learned = derive_learning_preferences(
            [
                {"rating": 5, "tags": ["strong_hook", "clear_story"]},
                {"rating": 4, "tags": ["strong_hook"]},
            ],
            minimum_samples=3,
        )

        self.assertEqual(learned["sample_size"], 2)
        self.assertEqual(learned["feedback_needed"], 1)
        self.assertEqual(learned["preferences"], [])

    def test_builds_explainable_preferences_from_repeated_evidence(self) -> None:
        learned = derive_learning_preferences(
            [
                {"rating": 5, "tags": ["strong_hook", "balanced_audio"]},
                {"rating": 4, "tags": ["strong_hook", "balanced_audio"]},
                {"rating": 5, "tags": ["strong_hook", "clear_story"]},
                {"rating": 3, "tags": ["audio_issue"]},
            ],
            minimum_samples=3,
        )

        preferences = {item["tag"]: item for item in learned["preferences"]}
        self.assertIn("strong_hook", preferences)
        self.assertIn("balanced_audio", preferences)
        self.assertEqual(preferences["strong_hook"]["evidence_count"], 3)
        self.assertEqual(preferences["strong_hook"]["sample_size"], 4)
        self.assertEqual(learned["average_rating"], 4.25)

    def test_conflicting_feedback_does_not_create_opposing_directives(self) -> None:
        learned = derive_learning_preferences(
            [
                {"rating": 3, "tags": ["pacing_too_slow"]},
                {"rating": 3, "tags": ["pacing_too_slow"]},
                {"rating": 3, "tags": ["pacing_too_fast"]},
                {"rating": 3, "tags": ["pacing_too_fast"]},
            ],
            minimum_samples=3,
        )

        self.assertFalse(
            any(item["dimension"] == "pacing" for item in learned["preferences"])
        )

    def test_feedback_schema_rejects_unknown_and_duplicate_tags(self) -> None:
        with self.assertRaises(ValidationError):
            EditFeedbackCreate.model_validate(
                {
                    "edit_run_id": str(uuid4()),
                    "rating": 5,
                    "tags": ["strong_hook", "strong_hook"],
                }
            )
        with self.assertRaises(ValidationError):
            EditFeedbackCreate.model_validate(
                {
                    "edit_run_id": str(uuid4()),
                    "rating": 5,
                    "tags": ["make_everything_viral"],
                }
            )
        with self.assertRaises(ValidationError):
            EditFeedbackCreate.model_validate(
                {
                    "edit_run_id": str(uuid4()),
                    "rating": 3,
                    "tags": ["strong_hook", "weak_hook"],
                }
            )

    def test_all_strengths_can_be_saved_and_read_back(self) -> None:
        strengths = [
            "strong_hook", "clear_story", "clean_captions", "balanced_audio",
            "good_visuals", "good_colour", "strong_ending", "effects_worked",
            "meme_worked",
        ]
        feedback = EditFeedbackCreate.model_validate({
            "edit_run_id": str(uuid4()), "rating": 5, "tags": strengths,
            "note": "Best edit yet", "would_use_again": True,
        })
        now = datetime.now(timezone.utc)
        response = EditFeedbackResponse.model_validate({
            **feedback.model_dump(), "id": uuid4(), "job_id": uuid4(),
            "created_at": now, "updated_at": now,
        })
        self.assertEqual(response.tags, strengths)
        self.assertTrue(response.would_use_again)

        # A detailed rating is still one example, not nine learning samples.
        learned = derive_learning_preferences([response.model_dump()], minimum_samples=3)
        self.assertEqual(learned["sample_size"], 1)
        self.assertEqual(learned["feedback_needed"], 2)
        self.assertEqual(learned["preferences"], [])

    def test_learning_threshold_cannot_be_lowered_below_three(self) -> None:
        with self.assertRaises(ValidationError):
            LearningSettingsUpdate.model_validate(
                {"enabled": True, "minimum_samples": 1}
            )

    def test_mature_local_preference_enters_prompt_as_bounded_guidance(self) -> None:
        settings = Settings(
            database_url="postgresql://example.invalid/test",
            upload_hook_secret="x" * 32,
        )
        context = {
            "job": {"recipe": "talking_head"},
            "project": {"privacy_mode": "text_only", "ai_copy_allowed": False},
            "assets": [],
            "music_library": [],
            "learning_preferences": {
                "enabled": True,
                "directives": ["Reach the strongest source-backed hook sooner."],
                "hosted_model_calls": 0,
            },
        }

        prompt = str(_model_content(context, settings)[0]["text"])

        self.assertIn("learned locally from repeated explicit user feedback", prompt)
        self.assertIn("Reach the strongest source-backed hook sooner", prompt)
        self.assertIn("never invent material", prompt)


if __name__ == "__main__":
    unittest.main()
