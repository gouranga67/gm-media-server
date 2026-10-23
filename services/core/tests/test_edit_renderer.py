import tempfile
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan
from app.edit_renderer import _create_delivery_package, caption_events, render_ass


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

    def test_applies_only_explicit_caption_replacements(self) -> None:
        asset_id = uuid4()
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "talking_head",
                "clips": [
                    {
                        "asset_id": str(asset_id),
                        "source_in": 0,
                        "source_out": 3,
                        "crop": "center_fill",
                        "transition": "cut",
                    }
                ],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Caption correction test.",
            }
        )
        events = caption_events(
            plan,
            [
                {
                    "asset_id": str(asset_id),
                    "transcript_segments": [
                        {"start": 0, "end": 2, "text": "Welcome to Sidney today"}
                    ],
                }
            ],
            [{"original_text": "Sidney", "replacement_text": "Sydney"}],
        )

        self.assertEqual(events[0]["text"], "Welcome to Sydney today")

    def test_scales_ass_layout_for_final_delivery(self) -> None:
        ass = render_ass(
            [{"start": 0, "end": 1, "text": "Final"}],
            width=1080,
            height=1920,
        )

        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("GMBlue,Arial,68", ass)

    def test_delivery_package_contains_only_named_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "video_path": root / "final.mp4",
                "captions_path": root / "captions.vtt",
                "cover_path": root / "cover.jpg",
                "manifest_path": root / "manifest.json",
            }
            for name, path in files.items():
                path.write_bytes(name.encode("utf-8"))
            destination = root / "delivery.zip"

            _create_delivery_package(destination, **files)

            self.assertEqual(destination.stat().st_mode & 0o777, 0o440)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "gm-studio-final.mp4",
                        "gm-studio-captions.vtt",
                        "gm-studio-cover.jpg",
                        "gm-studio-manifest.json",
                    },
                )

    def test_delivery_package_includes_opted_in_post_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "video_path": root / "final.mp4",
                "captions_path": root / "captions.vtt",
                "cover_path": root / "cover.jpg",
                "manifest_path": root / "manifest.json",
                "post_copy_path": root / "post-copy.txt",
            }
            for name, path in files.items():
                path.write_bytes(name.encode("utf-8"))
            destination = root / "delivery.zip"

            _create_delivery_package(destination, **files)

            with zipfile.ZipFile(destination) as archive:
                self.assertIn("gm-studio-post-copy.txt", archive.namelist())


if __name__ == "__main__":
    unittest.main()
