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

    def test_compact_context_preserves_editorial_evidence_and_full_transcripts(self):
        context = self.context()
        asset = context["assets"][0]
        asset.update(sha256="checksum", byte_size=1234, asset_status="ready")
        moment = {"asset_id": asset["asset_id"], "source_name": "original.mp4",
                  "text": "Keep this complete thought.", "start_seconds": 3, "end_seconds": 5,
                  "role_scores": {"hook": 0.8, "payoff": 0.2},
                  "score_components": {"hook": 0.8, "payoff": 0.3, "clarity": 0.9},
                  "edit_guidance": {"clean_cut_in": True, "pause_after_seconds": 0.4},
                  "signals": ["complete_spoken_thought"], "engagement_score": 0.75}
        asset["source_name"] = "original.mp4"
        asset["story_index"]["moments"] = [deepcopy(moment)] * 24
        original = deepcopy(context)
        public = _public_context(context, 120_000)
        compact = public["assets"][0]
        self.assertEqual(context, original, "rendering and validation keep their complete context")
        self.assertEqual(compact["transcript_segments"], asset["transcript_segments"])
        self.assertEqual(len(compact["story_index"]["moments"]), 24)
        for actual in compact["story_index"]["moments"]:
            self.assertNotIn("asset_id", actual)
            self.assertNotIn("source_name", actual)
            for key, value in moment.items():
                if key not in {"asset_id", "source_name", "score_components"}:
                    self.assertEqual(actual[key], value)
            for key, value in moment["score_components"].items():
                self.assertEqual(actual["score_components"].get(key, actual["role_scores"].get(key)), value)
        self.assertNotIn("sha256", compact)

    def test_compact_libraries_preserve_choices_and_local_rights_records(self):
        context = self.context()
        rights = {"license_name": "CC0", "license_source_url": "https://example.org/license",
                  "allowed_platforms": ["all_social"], "attribution": "Source credit", "_storage_key": "private"}
        context["job"].update(music_mode="present", effect_level="social")
        context["music_library"] = [dict(rights, track_id=str(i), title=f"Track {i}", mood="hopeful",
                                        energy="low", bpm=100, beat_grid_seconds=[0.1, 0.7]) for i in range(3)]
        context["creative_effect_library"] = [dict(rights, asset_id=str(i), title=f"Effect {i}",
            kind="sound_effect", tags=["reveal"], purpose="reveal", duration_seconds=0.5) for i in range(36)]
        original = deepcopy(context)
        public = _public_context(context, 120_000)
        self.assertEqual(context, original)
        for name in ("music_library", "creative_effect_library"):
            self.assertEqual(len(public[name]), len(context[name]))
            for actual, source in zip(public[name], context[name]):
                for key, value in source.items():
                    if key not in {"license_source_url", "allowed_platforms", "attribution", "_storage_key"}:
                        self.assertEqual(actual[key], value)
                self.assertNotIn("license_source_url", actual)

        context["job"]["selected_music_track_id"] = "1"
        selected = _public_context(context, 120_000)
        self.assertEqual([track["track_id"] for track in selected["music_library"]], ["1"])
        context["job"].update(music_mode="none", effect_level="off")
        disabled = _public_context(context, 120_000)
        self.assertEqual(disabled["music_library"], [])
        self.assertEqual(disabled["creative_effect_library"], [])

    def test_compact_prompt_preserves_revision_and_learned_directives(self):
        context = self.context()
        context["revision"] = {"mode": "targeted", "instruction": "Keep the original ending.",
                               "previous_plan": {"clips": [{"asset_id": "0", "source_in": 1, "source_out": 4}]},
                               "locked_elements": ["spoken phrases"]}
        context["learning_preferences"] = {"directives": ["Keep complete phrases."]}
        public = _public_context(context, 120_000)
        prompt = _model_content(context, SimpleNamespace(editor_max_context_characters=120_000))[0]["text"]
        self.assertTrue(prompt.endswith(json.dumps(public, ensure_ascii=False, separators=(",", ":"))))
        self.assertEqual(public["revision"], context["revision"])
        self.assertEqual(public["learning_preferences"], context["learning_preferences"])
        self.assertIn("Keep complete phrases.", prompt)

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
