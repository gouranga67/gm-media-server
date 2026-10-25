import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.edit_plan import (
    apply_timeline_adjustments,
    derive_duration_variant,
    edit_plan_duration,
    repair_predictable_plan_defaults,
    validate_edit_plan,
)


class EditPlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset_id = uuid4()
        self.assets = [
            {
                "asset_id": str(self.asset_id),
                "duration_seconds": 30.0,
                "has_video": True,
                "has_audio": True,
            }
        ]
        self.document = {
            "schema_version": "1.0",
            "recipe": "talking_head",
            "clips": [
                {
                    "asset_id": str(self.asset_id),
                    "source_in": 1.0,
                    "source_out": 8.5,
                    "crop": "center_fill",
                    "transition": "cut",
                }
            ],
            "caption_style": "clean_blue_v1",
            "audio_preset": "spoken_voice_v1",
            "end_card": "none",
            "editorial_summary": "A concise opening excerpt.",
        }

    def test_accepts_source_only_plan(self) -> None:
        plan = validate_edit_plan(self.document, self.assets)
        self.assertEqual(str(plan.clips[0].asset_id), str(self.asset_id))

    def test_rejects_invented_asset(self) -> None:
        self.document["clips"][0]["asset_id"] = str(uuid4())
        with self.assertRaisesRegex(ValueError, "does not belong"):
            validate_edit_plan(self.document, self.assets)

    def test_rejects_out_of_range_timecode(self) -> None:
        self.document["clips"][0]["source_out"] = 31.0
        with self.assertRaisesRegex(ValueError, "before requested"):
            validate_edit_plan(self.document, self.assets)

    def test_rejects_unknown_effect_field(self) -> None:
        self.document["clips"][0]["effect"] = "generate_b_roll"
        with self.assertRaises(ValidationError):
            validate_edit_plan(self.document, self.assets)

    def test_post_copy_requires_explicit_project_permission(self) -> None:
        self.document["post_copy"] = "A source-grounded social caption."
        with self.assertRaisesRegex(ValueError, "not enabled"):
            validate_edit_plan(self.document, self.assets)

        plan = validate_edit_plan(self.document, self.assets, allow_post_copy=True)
        self.assertEqual(plan.post_copy, "A source-grounded social caption.")

    def test_rejects_preview_over_sixty_seconds(self) -> None:
        second_id = uuid4()
        self.assets.append(
            {
                "asset_id": str(second_id),
                "duration_seconds": 40.0,
                "has_video": True,
                "has_audio": True,
            }
        )
        self.document["clips"] = [
            {**self.document["clips"][0], "source_in": 0, "source_out": 30},
            {
                **self.document["clips"][0],
                "asset_id": str(second_id),
                "source_in": 0,
                "source_out": 31,
            },
        ]
        with self.assertRaisesRegex(ValueError, "exceeds 60 seconds"):
            validate_edit_plan(self.document, self.assets)

    def test_new_visual_fields_remain_backward_compatible(self) -> None:
        plan = validate_edit_plan(self.document, self.assets)

        self.assertEqual(plan.clips[0].visual_preset, "standard")
        self.assertEqual(plan.clips[0].story_role, "development")
        self.assertEqual(plan.clips[0].editorial_intent, "")
        self.assertEqual(plan.music_mix, "none")

    def test_enforces_requested_duration_when_footage_is_available(self) -> None:
        self.assets[0]["duration_seconds"] = 60.0
        with self.assertRaisesRegex(ValueError, "below the 36.000s floor"):
            validate_edit_plan(
                self.document,
                self.assets,
                creative_direction={"target_duration_seconds": 45},
            )

    def test_rejects_short_animated_zoom(self) -> None:
        self.document["clips"][0].update(
            source_in=1.0,
            source_out=2.5,
            visual_preset="slow_push_in",
        )
        with self.assertRaisesRegex(ValueError, "at least 2 seconds"):
            validate_edit_plan(self.document, self.assets)

    def test_calm_style_rejects_strong_punch_in(self) -> None:
        self.document["clips"][0]["visual_preset"] = "strong_punch_in"
        with self.assertRaisesRegex(ValueError, "calm style"):
            validate_edit_plan(
                self.document,
                self.assets,
                creative_direction={"edit_style": "calm"},
            )

    def test_energetic_style_requires_visual_emphasis(self) -> None:
        self.document["clips"][0].update(source_in=0, source_out=10)
        with self.assertRaisesRegex(ValueError, "requires at least one"):
            validate_edit_plan(
                self.document,
                self.assets,
                creative_direction={"edit_style": "energetic"},
            )

    def test_music_must_come_from_approved_library(self) -> None:
        track_id = uuid4()
        self.document.update(
            music_track_id=str(track_id),
            music_mix="subtle",
        )
        plan = validate_edit_plan(
            self.document,
            self.assets,
            creative_direction={"music_mode": "subtle"},
            music_tracks=[{"track_id": str(track_id)}],
        )
        self.assertEqual(plan.music_track_id, track_id)

        with self.assertRaisesRegex(ValueError, "not in the approved library"):
            validate_edit_plan(
                self.document,
                self.assets,
                creative_direction={"music_mode": "subtle"},
                music_tracks=[],
            )

    def test_revision_repair_removes_music_when_job_is_voice_only(self) -> None:
        track_id = uuid4()
        proposed = {**self.document, "music_track_id": str(track_id), "music_mix": "subtle"}

        repaired, repairs = repair_predictable_plan_defaults(
            proposed,
            creative_direction={"music_mode": "none"},
            music_tracks=[{"track_id": str(track_id)}],
            previous_plan=self.document,
        )

        self.assertIsNone(repaired["music_track_id"])
        self.assertEqual(repaired["music_mix"], "none")
        self.assertIn("removed_unrequested_music", repairs)

    def test_validator_enforces_voice_only_job_for_stale_plans(self) -> None:
        track_id = uuid4()
        self.document.update(
            music_track_id=str(track_id),
            music_mix="subtle",
        )

        plan = validate_edit_plan(
            self.document,
            self.assets,
            creative_direction={"music_mode": "none"},
            music_tracks=[{"track_id": str(track_id)}],
        )

        self.assertIsNone(plan.music_track_id)
        self.assertEqual(plan.music_mix, "none")

    def test_spoken_word_boundaries_receive_small_safety_handles(self) -> None:
        self.assets[0]["transcript_segments"] = [{
            "start": 1.0,
            "end": 2.1,
            "text": "Clear spoken phrase",
            "words": [
                {"start": 1.0, "end": 1.35, "text": "Clear"},
                {"start": 1.35, "end": 1.72, "text": "spoken"},
                {"start": 1.72, "end": 2.1, "text": "phrase"},
            ],
        }]
        self.document["clips"][0].update(source_in=1.05, source_out=2.0)

        plan = validate_edit_plan(self.document, self.assets)

        self.assertEqual(plan.clips[0].source_in, 0.88)
        self.assertEqual(plan.clips[0].source_out, 2.26)

    def test_duration_variant_trims_without_changing_source_order(self) -> None:
        self.document["clips"] = [
            {**self.document["clips"][0], "source_in": 0, "source_out": 8},
            {**self.document["clips"][0], "source_in": 10, "source_out": 20},
        ]
        plan = validate_edit_plan(self.document, self.assets)

        variant = derive_duration_variant(plan, 15)

        self.assertAlmostEqual(edit_plan_duration(variant), 15)
        self.assertEqual(variant.clips[0].source_in, 0)
        self.assertEqual(variant.clips[1].source_out, 17)

    def test_duration_variant_keeps_shorter_approved_edit(self) -> None:
        plan = validate_edit_plan(self.document, self.assets)

        variant = derive_duration_variant(plan, 15)

        self.assertAlmostEqual(edit_plan_duration(variant), 7.5)

    def test_timeline_adjustments_reorder_and_change_framing_without_model(self) -> None:
        self.document["clips"] = [
            {**self.document["clips"][0], "source_in": 0, "source_out": 5},
            {**self.document["clips"][0], "source_in": 10, "source_out": 15},
        ]
        plan = validate_edit_plan(self.document, self.assets)

        adjusted = apply_timeline_adjustments(
            plan,
            [{"clip_index": 1, "action": "move_up", "visual_preset": "punch_in"}],
        )

        self.assertEqual(adjusted.clips[0].source_in, 10)
        self.assertEqual(adjusted.clips[0].visual_preset, "punch_in")
        self.assertEqual(adjusted.clips[0].transition, "cut")

    def test_timeline_adjustment_shortens_internal_pauses_without_model(self) -> None:
        self.document["clips"] = [
            {**self.document["clips"][0], "source_in": 0, "source_out": 8},
        ]
        self.assets[0]["transcript_segments"] = [{
            "start": 0,
            "end": 8,
            "text": "setup reaction payoff",
            "words": [
                {"start": 0.5, "end": 1.0, "text": "setup"},
                {"start": 4.0, "end": 4.5, "text": "reaction"},
                {"start": 7.0, "end": 7.5, "text": "payoff"},
            ],
        }]
        plan = validate_edit_plan(self.document, self.assets)

        adjusted = apply_timeline_adjustments(
            plan,
            [{"clip_index": 0, "action": "keep", "max_pause_seconds": 0.6}],
            self.assets,
        )

        self.assertEqual(len(adjusted.clips), 3)
        self.assertLess(edit_plan_duration(adjusted), edit_plan_duration(plan) - 4)
        self.assertAlmostEqual(adjusted.clips[1].source_in, 3.7)
        self.assertAlmostEqual(adjusted.clips[1].source_out, 4.8)

    def test_timeline_adjustment_shortens_leading_comic_pause(self) -> None:
        self.document["clips"] = [
            {**self.document["clips"][0], "source_in": 49.45, "source_out": 53.52},
        ]
        self.assets[0]["duration_seconds"] = 90
        self.assets[0]["transcript_segments"] = [{
            "start": 51.86,
            "end": 53.36,
            "text": "was terrible wasn't it",
            "words": [
                {"start": 51.86, "end": 52.1, "text": "was"},
                {"start": 52.2, "end": 52.7, "text": "terrible"},
                {"start": 52.8, "end": 53.36, "text": "wasn't it"},
            ],
        }]
        plan = validate_edit_plan(self.document, self.assets)

        adjusted = apply_timeline_adjustments(
            plan,
            [{"clip_index": 0, "action": "keep", "max_pause_seconds": 0.6}],
            self.assets,
        )

        self.assertEqual(len(adjusted.clips), 1)
        self.assertAlmostEqual(adjusted.clips[0].source_in, 51.26)
        self.assertAlmostEqual(adjusted.clips[0].source_out, 53.52)


if __name__ == "__main__":
    unittest.main()
