import unittest

from pydantic import ValidationError

from app.editing import (
    _job_history_kind,
    _needs_montage_delivery_refresh,
    _validate_caption_corrections,
)
from app.schemas import DeliveryVariantCreate, JobAssetAttach, JobCreate, LibraryAssetUpdate, LibraryCollectionCreate, RevisionCreate


class RevisionSchemaTests(unittest.TestCase):
    def test_story_rebuild_requires_a_note_and_unlocked_selections(self) -> None:
        with self.assertRaisesRegex(ValidationError, "describe the story"):
            RevisionCreate(revision_mode="rebuild_story")
        with self.assertRaisesRegex(ValidationError, "unlock clip order"):
            RevisionCreate(note="Rebuild around the brief", revision_mode="rebuild_story",
                           locked_elements=["clip order"])

    def test_story_rebuild_preserves_other_protections(self) -> None:
        revision = RevisionCreate(note="Keep the explanation together", revision_mode="rebuild_story",
                                  locked_elements=["music", "effects"])
        self.assertEqual(revision.revision_mode, "rebuild_story")
        self.assertEqual(revision.locked_elements, ["music", "effects"])

    def test_caption_validation_matches_rendered_words_without_case_or_punctuation(self) -> None:
        context = {
            "assets": [{
                "transcript_segments": [{
                    "text": "Different normalized segment text",
                    "words": [{"text": "Costa"}, {"text": "Royal!"}],
                }],
            }],
        }

        _validate_caption_corrections(
            context,
            [{"original_text": "costa royal", "replacement_text": "castor oil"}],
        )

    def test_labels_only_reserved_verification_project_names_as_tests(self) -> None:
        self.assertEqual(_job_history_kind("Phase 3 verification — 2026-10-24"), "verification")
        self.assertEqual(_job_history_kind("Phase 6C library verification"), "verification")
        self.assertEqual(_job_history_kind("Phase 16 effects verification"), "verification")
        self.assertEqual(_job_history_kind("Interesting montage"), "editing")

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
        self.assertEqual(job.audience, "")
        self.assertEqual(job.story_goal, "")

    def test_story_direction_is_bounded_and_normalized(self) -> None:
        job = JobCreate(
            audience="  curious   first-time viewers ",
            story_goal="  Understand the main point.  ",
            desired_feeling="  surprised, then reassured ",
            ending_instruction="  End on the laugh. ",
        )

        self.assertEqual(job.audience, "curious first-time viewers")
        self.assertEqual(job.story_goal, "Understand the main point.")
        self.assertEqual(job.desired_feeling, "surprised, then reassured")
        self.assertEqual(job.ending_instruction, "End on the laugh.")
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

    def test_accepts_square_jobs_and_delivery_variants(self) -> None:
        job = JobCreate(output_aspect="square")
        variant = DeliveryVariantCreate(output_aspect="square", target_duration_seconds=15)

        self.assertEqual(job.output_aspect.value, "square")
        self.assertEqual(variant.output_aspect.value, "square")

    def test_rejects_unsafe_model_slug(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unsupported characters"):
            JobCreate(editor_model="model/name")

    def test_library_attach_requires_unique_assets(self) -> None:
        asset_id = "11111111-1111-4111-8111-111111111111"

        with self.assertRaisesRegex(ValidationError, "cannot repeat"):
            JobAssetAttach(asset_ids=[asset_id, asset_id])

    def test_library_attach_accepts_multiple_assets(self) -> None:
        attachment = JobAssetAttach(
            asset_ids=[
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
            ]
        )

        self.assertEqual(len(attachment.asset_ids), 2)

    def test_library_metadata_normalizes_name_and_unique_tags(self) -> None:
        metadata = LibraryAssetUpdate.model_validate(
            {
                "display_name": "  Fighter   jet flypast ",
                "notes": "Useful source",
                "favorite": True,
                "tags": [" Aviation ", "travel", "AVIATION"],
            }
        )

        self.assertEqual(metadata.display_name, "Fighter jet flypast")
        self.assertEqual(metadata.tags, ["aviation", "travel"])

    def test_library_metadata_rejects_oversized_tag(self) -> None:
        with self.assertRaisesRegex(ValidationError, "between 1 and 40"):
            LibraryAssetUpdate(tags=["x" * 41])

    def test_collection_name_is_normalized(self) -> None:
        collection = LibraryCollectionCreate(name="  Travel   B-roll ")

        self.assertEqual(collection.name, "Travel B-roll")

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

    def test_accepts_bounded_local_timeline_adjustment_and_locks(self) -> None:
        revision = RevisionCreate.model_validate(
            {
                "clip_adjustments": [{"clip_index": 1, "action": "move_up", "source_audio_gain_db": 4}],
                "locked_elements": ["captions", "music"],
            }
        )

        self.assertEqual(revision.clip_adjustments[0].clip_index, 1)
        self.assertEqual(revision.locked_elements, ["captions", "music"])

    def test_accepts_pause_and_platform_safe_caption_controls(self) -> None:
        revision = RevisionCreate.model_validate(
            {
                "clip_adjustments": [{
                    "clip_index": 2,
                    "max_pause_seconds": 0.6,
                }],
                "caption_settings": {
                    "position": "lower_safe",
                    "timing_offset_seconds": -0.15,
                },
            }
        )

        self.assertEqual(revision.clip_adjustments[0].max_pause_seconds, 0.6)
        self.assertEqual(revision.caption_settings.position, "lower_safe")
        self.assertEqual(revision.caption_settings.timing_offset_seconds, -0.15)


if __name__ == "__main__":
    unittest.main()
