import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.story_intelligence import (
    STORY_INTELLIGENCE_VERSION,
    build_story_assessment,
    build_story_moments,
    select_story_moments,
)


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
                            {"start": 0.4, "end": 2.8, "text": "Why did this actually work?", "words": [{"probability": 0.94}]},
                            {"start": 3.0, "end": 6.0, "text": "Because we tested the idea carefully.", "words": [{"probability": 0.91}]},
                            {"start": 8.0, "end": 9.5, "text": "Try it today and tell us.", "words": [{"probability": 0.89}]},
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
        self.assertIn("faster-whisper-small", spoken[0]["evidence"])
        self.assertEqual((spoken[0]["start_seconds"], spoken[0]["end_seconds"]), (0.4, 2.8))
        self.assertEqual(STORY_INTELLIGENCE_VERSION, "1.1")
        self.assertIn("engagement_score", spoken[0])
        self.assertTrue(spoken[0]["edit_guidance"]["clean_cut_in"])
        self.assertGreater(spoken[0]["score_components"]["hook"], 0.5)

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

    def test_story_assessment_reports_coverage_duplicates_and_zero_hosted_calls(self) -> None:
        moments = [
            {"asset_id": "a", "moment_id": "1", "kind": "spoken", "text": "Why does this work?", "suggested_roles": ["hook"], "role_scores": {"hook": 0.9}, "edit_guidance": {"clean_cut_in": True, "clean_cut_out": True}},
            {"asset_id": "b", "moment_id": "2", "kind": "spoken", "text": "Why does this work?", "suggested_roles": ["hook"], "role_scores": {"hook": 0.8}, "edit_guidance": {"clean_cut_in": True, "clean_cut_out": True}},
            {"asset_id": "a", "moment_id": "3", "kind": "spoken", "text": "Because this is the answer.", "suggested_roles": ["development", "payoff"], "role_scores": {"development": 0.7, "payoff": 0.9}, "edit_guidance": {"clean_cut_in": True, "clean_cut_out": True}},
        ]
        assessment = build_story_assessment(moments)

        self.assertTrue(assessment["coverage"]["hook"])
        self.assertTrue(assessment["coverage"]["payoff"])
        self.assertIn("ending", assessment["gaps"])
        self.assertEqual(len(assessment["duplicate_idea_groups"]), 1)
        self.assertEqual(assessment["clean_spoken_edit_points"], 3)
        self.assertEqual(assessment["hosted_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
