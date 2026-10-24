import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.edit_plan import derive_duration_variant, edit_plan_duration, validate_edit_plan


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


if __name__ == "__main__":
    unittest.main()
