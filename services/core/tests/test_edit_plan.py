import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.edit_plan import validate_edit_plan


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


if __name__ == "__main__":
    unittest.main()
