import unittest
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan
from app.edit_renderer import caption_events, render_ass


class CaptionMappingTests(unittest.TestCase):
    def test_maps_source_captions_to_concatenated_timeline(self) -> None:
        first = uuid4()
        second = uuid4()
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "talking_head",
                "clips": [
                    {
                        "asset_id": str(first),
                        "source_in": 10,
                        "source_out": 15,
                        "crop": "center_fill",
                        "transition": "cut",
                    },
                    {
                        "asset_id": str(second),
                        "source_in": 2,
                        "source_out": 5,
                        "crop": "center_fill",
                        "transition": "cut",
                    },
                ],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Two source excerpts.",
            }
        )
        assets = [
            {
                "asset_id": str(first),
                "transcript_segments": [{"start": 11, "end": 12, "text": "First"}],
            },
            {
                "asset_id": str(second),
                "transcript_segments": [{"start": 3, "end": 4, "text": "Second"}],
            },
        ]

        events = caption_events(plan, assets)

        self.assertEqual(events[0], {"start": 1.0, "end": 2.0, "text": "First"})
        self.assertEqual(events[1], {"start": 6.0, "end": 7.0, "text": "Second"})
        ass = render_ass(events)
        self.assertIn("0:00:01.00,0:00:02.00", ass)
        self.assertIn("0:00:06.00,0:00:07.00", ass)


if __name__ == "__main__":
    unittest.main()
