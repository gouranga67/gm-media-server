import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.composition import append_green_screen_background
from app.schemas import JobComposition


class JobCompositionTests(unittest.TestCase):
    def test_green_screen_requires_two_distinct_sources(self) -> None:
        foreground = uuid4()
        with self.assertRaises(ValidationError):
            JobComposition(mode="green_screen", foreground_asset_id=foreground)
        with self.assertRaises(ValidationError):
            JobComposition(
                mode="green_screen",
                foreground_asset_id=foreground,
                background_asset_id=foreground,
            )

    def test_green_screen_tuning_is_bounded(self) -> None:
        foreground = uuid4()
        background = uuid4()
        tuned = JobComposition(
            mode="green_screen",
            foreground_asset_id=foreground,
            background_asset_id=background,
            chroma_key_color="#0000FF",
            chroma_similarity=0.2,
            chroma_blend=0.1,
            spill_suppression=0.35,
        )
        self.assertEqual(tuned.chroma_key_color, "#0000FF")
        with self.assertRaises(ValidationError):
            JobComposition(
                mode="green_screen",
                foreground_asset_id=foreground,
                background_asset_id=background,
                chroma_similarity=0.8,
            )

    def test_graph_keys_foreground_before_reapplying_captions(self) -> None:
        graph = "[0:v]null[base];[base]subtitles=filename='captions.ass'[vout];[0:a]anull[aout]"
        result = append_green_screen_background(
            graph,
            {"input_index": 1, "media_kind": "image", "path": "background.jpg", "hdr_mode": None},
            width=540,
            height=960,
            fps=30,
            duration=8,
        )

        self.assertIn("[1:v:0]scale=540:960", result)
        self.assertIn("chromakey=0x00FF00:0.1200:0.0800", result)
        self.assertIn("[compositionbackground][compositionkeyed]overlay=", result)
        self.assertLess(result.index("chromakey="), result.index("subtitles="))

    def test_graph_uses_saved_key_tuning_and_spill_suppression(self) -> None:
        result = append_green_screen_background(
            "[0:v]null[vout];[0:a]anull[aout]",
            {"input_index": 1, "media_kind": "image", "path": "background.jpg", "hdr_mode": None},
            width=540,
            height=960,
            fps=30,
            duration=8,
            composition={
                "chroma_key_color": "#0000FF",
                "chroma_similarity": 0.2,
                "chroma_blend": 0.1,
                "spill_suppression": 0.35,
            },
        )
        self.assertIn("chromakey=0x0000FF:0.2000:0.1000", result)
        self.assertIn("despill=type=blue:mix=0.3500", result)


if __name__ == "__main__":
    unittest.main()
