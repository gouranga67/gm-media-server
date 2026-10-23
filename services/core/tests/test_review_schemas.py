import unittest

from pydantic import ValidationError

from app.editing import _needs_montage_delivery_refresh
from app.schemas import JobCreate, RevisionCreate


class RevisionSchemaTests(unittest.TestCase):
    def test_only_legacy_ready_montage_delivery_needs_refresh(self) -> None:
        legacy = {"status": "ready", "manifest": {"recipe": "montage"}}
        current = {
            "status": "ready",
            "manifest": {"captions": {"style": "clean_blue_v1"}},
        }

        self.assertTrue(_needs_montage_delivery_refresh({"recipe": "montage"}, legacy))
        self.assertFalse(_needs_montage_delivery_refresh({"recipe": "montage"}, current))
        self.assertFalse(_needs_montage_delivery_refresh({"recipe": "talking_head"}, legacy))

    def test_new_job_has_safe_creative_defaults(self) -> None:
        job = JobCreate()

        self.assertEqual(job.target_duration_seconds, 45)
        self.assertEqual(job.edit_style.value, "energetic")
        self.assertEqual(job.music_mode.value, "none")
        self.assertEqual(job.target_platform.value, "all_social")
        self.assertEqual(job.reasoning_effort.value, "medium")
        self.assertEqual(job.output_aspect.value, "vertical")

    def test_accepts_montage_model_controls(self) -> None:
        job = JobCreate.model_validate(
            {
                "recipe": "montage",
                "target_duration_seconds": 15,
                "editor_model": "gpt-5-mini",
                "reasoning_effort": "low",
                "output_aspect": "landscape",
            }
        )

        self.assertEqual(job.recipe.value, "montage")
        self.assertEqual(job.editor_model, "gpt-5-mini")
        self.assertEqual(job.output_aspect.value, "landscape")

    def test_rejects_unsafe_model_slug(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unsupported characters"):
            JobCreate(editor_model="model/name")

    def test_requires_feedback_or_caption_correction(self) -> None:
        with self.assertRaises(ValidationError):
            RevisionCreate()

    def test_normalizes_feedback_and_caption_text(self) -> None:
        revision = RevisionCreate.model_validate(
            {
                "note": "  Shorten   the opening. ",
                "caption_corrections": [
                    {
                        "original_text": "  Sidney ",
                        "replacement_text": " Sydney ",
                    }
                ],
            }
        )

        self.assertEqual(revision.note, "Shorten the opening.")
        self.assertEqual(revision.caption_corrections[0].original_text, "Sidney")
        self.assertEqual(revision.caption_corrections[0].replacement_text, "Sydney")

    def test_rejects_duplicate_caption_targets(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot repeat"):
            RevisionCreate.model_validate(
                {
                    "caption_corrections": [
                        {"original_text": "Sidney", "replacement_text": "Sydney"},
                        {"original_text": "Sidney", "replacement_text": "Sydney, Australia"},
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
