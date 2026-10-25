import json
import unittest
from copy import deepcopy
from types import SimpleNamespace

from app.editor_provider import ProviderResponseError, _model_content, _public_context
from app.revision_report import compare_revision


class RevisionContextTests(unittest.TestCase):
    def context(self):
        return {
            "project": {"privacy_mode": "transcript_only", "brief": "Explain the problem then the result."},
            "job": {"recipe": "talking_head"},
            "assets": [{"asset_id": str(index), "_storage_key": "private/source.mp4",
                        "transcript_segments": [
                            {"start": n, "end": n + 1, "text": f"Source {index} sentence {n}: " + "dialogue " * 12}
                            for n in range(32)],
                        "story_index": {"moments": [{"text": "A highlight."}]}}
                       for index in range(3)],
        }

    def test_moment_cards_do_not_replace_complete_dialogue(self):
        context = self.context()
        public = _public_context(context, 120_000)
        self.assertEqual(len(public["assets"][0]["transcript_segments"]), 32)
        self.assertNotIn("_storage_key", public["assets"][0])
        self.assertIn("_storage_key", context["assets"][0])

    def test_small_budget_keeps_all_sources_and_endings(self):
        public = _public_context(self.context(), 6_000)
        self.assertLessEqual(len(json.dumps(public, ensure_ascii=False, separators=(",", ":"))), 6_000)
        for asset in public["assets"]:
            self.assertTrue(asset["transcript_truncated"])
            segments = asset["transcript_segments"]
            self.assertEqual(segments[0]["start"], 0)
            self.assertEqual(segments[-1]["start"], 31)
            self.assertEqual([s["start"] for s in segments], sorted(s["start"] for s in segments))

    def test_oversize_inventory_fails_explicitly(self):
        with self.assertRaises(ProviderResponseError):
            _public_context({"assets": [], "huge_inventory": "x" * 2000}, 1000)

    def test_rebuild_instruction_is_explicit_and_reaches_prompt(self):
        context = self.context()
        context["revision"] = {"mode": "rebuild_story", "instruction": "Keep the explanation together.",
                               "previous_plan": {"clips": []}, "locked_elements": ["music"]}
        settings = SimpleNamespace(editor_max_context_characters=120_000)
        prompt = _model_content(context, settings)[0]["text"]
        self.assertIn("Keep the explanation together.", prompt)
        self.assertIn("rejected draft", prompt)
        self.assertIn("music", prompt)
        self.assertIn("sentence 31", prompt)

    def test_summary_changes_do_not_count_as_edit_changes(self):
        before = {"clips": [{"asset_id": "one", "source_in": 0, "source_out": 4}],
                  "editorial_summary": "Original", "schema_version": "1.2"}
        after = {**deepcopy(before), "editorial_summary": "Completely rebuilt!", "schema_version": "1.3"}
        report = compare_revision(before, after)
        self.assertFalse(report["changed"])
        self.assertIn("same cut", report["notice"])

    def test_retimed_selection_is_reported(self):
        before = {"clips": [{"asset_id": "one", "source_in": 0, "source_out": 4}]}
        after = {"clips": [{"asset_id": "one", "source_in": 1, "source_out": 3}]}
        self.assertTrue(compare_revision(before, after)["changed"])

    def test_music_only_change_is_reported(self):
        report = compare_revision({"clips": [], "music_mix": "subtle"},
                                  {"clips": [], "music_mix": "present"})
        self.assertEqual(report["changes"], ["Music level changed."])


if __name__ == "__main__":
    unittest.main()
