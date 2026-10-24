import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.content_catalog import build_catalog_segments


class ContentCatalogTests(unittest.TestCase):
    def test_builds_evidence_backed_transcript_and_scene_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript = root / "analysis" / "asset" / "transcript.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "segments": [
                            {"start": 1.25, "end": 3.5, "text": "  The coastal path.  "},
                            {"start": 4.0, "end": 5.2, "text": "A second thought."},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manifest = {
                "probe": {"format": {"duration_seconds": 10.0}, "streams": [{"type": "video"}]},
                "derived": {
                    "transcript": "analysis/asset/transcript.json",
                    "scene_boundaries_seconds": [6.0, 3.0, 6.0],
                },
            }
            asset = {
                "source_name": "coast.mp4",
                "mime_type": "video/mp4",
                "sha256": "a" * 64,
            }

            segments = build_catalog_segments(
                asset,
                manifest,
                SimpleNamespace(media_root=root),  # type: ignore[arg-type]
            )

        transcripts = [segment for segment in segments if segment["segment_kind"] == "transcript"]
        scenes = [segment for segment in segments if segment["segment_kind"] == "scene"]
        self.assertEqual([segment["text"] for segment in transcripts], ["The coastal path.", "A second thought."])
        self.assertEqual(
            [(segment["start_seconds"], segment["end_seconds"]) for segment in scenes],
            [(0.0, 3.0), (3.0, 6.0), (6.0, 10.0)],
        )
        self.assertTrue(all(segment["source_model"] for segment in segments))

    def test_indexes_image_technical_facts_without_inventing_a_description(self) -> None:
        manifest = {
            "probe": {
                "format": {"duration_seconds": 0},
                "streams": [{"type": "video", "width": 4032, "height": 3024}],
            },
            "derived": {},
        }
        segments = build_catalog_segments(
            {"source_name": "market.jpg", "mime_type": "image/jpeg", "sha256": "b" * 64},
            manifest,
            SimpleNamespace(media_root=Path("/tmp")),  # type: ignore[arg-type]
        )

        image = next(segment for segment in segments if segment["segment_kind"] == "image")
        self.assertEqual(image["facts"], {"width": 4032, "height": 3024})
        self.assertEqual(image["source_model"], "ffprobe")
        self.assertNotIn("people", image["text"].lower())


if __name__ == "__main__":
    unittest.main()
