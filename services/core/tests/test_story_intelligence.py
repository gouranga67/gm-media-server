import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.story_intelligence import build_story_moments, select_story_moments


class StoryIntelligenceTests(unittest.TestCase):
    def test_builds_source_timed_story_roles_without_hosted_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript = root / "analysis" / "asset" / "transcript.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "segments": [
                            {"start": 0.4, "end": 2.8, "text": "Why did this actually work?"},
                            {"start": 3.0, "end": 6.0, "text": "Because we tested the idea carefully."},
                            {"start": 8.0, "end": 9.5, "text": "Try it today and tell us."},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            moments = build_story_moments(
                {"mime_type": "video/mp4"},
                {
                    "probe": {"format": {"duration_seconds": 10}},
                    "derived": {
                        "transcript": "analysis/asset/transcript.json",
                        "scene_boundaries_seconds": [5],
                    },
                },
                SimpleNamespace(media_root=root),  # type: ignore[arg-type]
            )

        spoken = [moment for moment in moments if moment["kind"] == "spoken"]
        self.assertEqual(len(spoken), 3)
        self.assertIn("hook", spoken[0]["suggested_roles"])
        self.assertIn("payoff", spoken[1]["suggested_roles"])
        self.assertIn("ending", spoken[2]["suggested_roles"])
        self.assertEqual(spoken[0]["evidence"], ["faster-whisper-small"])
        self.assertEqual((spoken[0]["start_seconds"], spoken[0]["end_seconds"]), (0.4, 2.8))

    def test_local_retrieval_prefers_matching_moment_and_keeps_story_edges(self) -> None:
        moments = [
            {"kind": "spoken", "text": "Opening setup", "intrinsic_score": 0.4},
            {"kind": "spoken", "text": "A fighter jet crosses the sky", "intrinsic_score": 0.4},
            {"kind": "spoken", "text": "Closing thought", "intrinsic_score": 0.4},
        ]
        selected = select_story_moments(moments, "fighter jet", limit=3)

        self.assertEqual(selected[0]["text"], "A fighter jet crosses the sky")
        self.assertEqual({item["text"] for item in selected}, {item["text"] for item in moments})
        self.assertGreater(selected[0]["retrieval_score"], selected[1]["retrieval_score"])


if __name__ == "__main__":
    unittest.main()
