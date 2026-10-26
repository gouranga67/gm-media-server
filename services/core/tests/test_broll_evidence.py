import base64
import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from PIL import Image

from app.broll_evidence import broll_guidance, guard_broll, speech_ranges
from app.edit_plan import TalkingHeadEditPlan, validate_edit_plan
from app.editor_provider import _model_content
from app.editor_visual_context import high_impact_visuals


class BrollEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.voice, self.cover, self.still = [str(uuid4()) for _ in range(3)]
        self.assets = [{"asset_id": self.voice, "has_video": True, "has_audio": True, "duration_seconds": 10},
                       {"asset_id": self.cover, "has_video": True, "has_audio": True, "duration_seconds": 10,
                        "transcript_segments": [{"start": 0, "end": 10, "text": "First thought. Last thought.",
                            "words": [{"start": 1, "end": 2, "text": "First thought."},
                                      {"start": 8, "end": 9, "text": "Last thought."}]}]},
                       {"asset_id": self.still, "mime_type": "image/jpeg"}]
        self.plan = TalkingHeadEditPlan.model_validate({"schema_version": "1.4", "recipe": "talking_head",
            "clips": [{"asset_id": self.voice, "source_in": 0, "source_out": 10, "crop": "center_fill", "visual_preset": "rhythmic_punch"}],
            "caption_style": "clean_blue_v1", "audio_preset": "spoken_voice_v1", "end_card": "none",
            "editorial_summary": "Keep this complete story.", "broll": [
                {"asset_id": self.cover, "media_kind": "video", "source_in": 1, "source_out": 3,
                 "start_seconds": 2, "duration_seconds": 2, "editorial_intent": "Different take holding the product."},
                {"asset_id": self.still, "media_kind": "image", "source_in": 0, "source_out": 0,
                 "start_seconds": 5, "duration_seconds": 1, "editorial_intent": "Product still."}]})

    def test_speaking_cutaway_is_removed_without_recutting_dialogue_or_other_overlays(self):
        original = self.plan.model_dump(mode="json")
        guarded, removed = guard_broll(self.plan, self.assets)
        self.assertEqual(guarded.clips, self.plan.clips)
        self.assertEqual(guarded.broll, self.plan.broll[1:])
        self.assertEqual(removed[0]["asset_id"], self.cover)
        self.assertEqual(removed[0]["reason"], "source_speech_overlaps_silent_cutaway")
        self.assertEqual(self.plan.model_dump(mode="json"), original)

    def test_real_word_gaps_remain_available_despite_a_long_transcript_segment(self):
        self.plan.broll[0].source_in, self.plan.broll[0].source_out = 3, 5
        guarded, removed = guard_broll(self.plan, self.assets)
        self.assertEqual(len(guarded.broll), 2)
        self.assertEqual(removed, [])
        windows = broll_guidance(self.assets[1])["speech_free_windows"]
        self.assertIn({"source_in": 2.15, "source_out": 7.85}, windows)

    def test_segment_times_are_conservative_when_word_times_are_missing(self):
        self.assets[1]["transcript_segments"][0].pop("words")
        self.plan.broll[0].source_in, self.plan.broll[0].source_out = 3, 5
        self.assertEqual(len(guard_broll(self.plan, self.assets)[0].broll), 1)
        self.assertEqual(broll_guidance(self.assets[1])["speech_free_windows"], [])

    def test_no_transcribed_speech_is_a_candidate_not_a_face_detection_claim(self):
        asset = {"asset_id": "quiet", "has_video": True, "has_audio": True, "duration_seconds": 2.5,
                 "transcript_segments": []}
        guide = broll_guidance(asset)
        self.assertEqual(guide["kind"], "no_transcribed_speech")
        self.assertEqual(guide["speech_free_windows"], [{"source_in": 0, "source_out": 2.5}])
        self.assertIn("not a face detector", guide["note"])
        self.assertEqual(broll_guidance(self.assets[2])["kind"], "still_candidate")

    def test_guard_does_not_hide_unknown_source_ids_from_the_validator(self):
        self.plan.broll[0].asset_id = uuid4()
        guarded, removed = guard_broll(self.plan, self.assets)
        self.assertEqual(removed, [])
        with self.assertRaisesRegex(ValueError, "does not belong"):
            validate_edit_plan(guarded.model_dump(mode="json"), self.assets, creative_direction={"edit_style": "high_impact"})

    def test_speech_padding_and_malformed_timestamps(self):
        asset = {"transcript_segments": [{"start": 0, "end": 2, "text": "A line.", "words": [
            {"start": 0.1, "end": 1, "text": "A"}, {"start": 1.1, "end": 2, "text": "line."},
            {"start": float("nan"), "end": 3, "text": "invalid"}]}]}
        self.assertEqual(speech_ranges(asset), [(0, 2.15)])


class BrollVisualContextTests(unittest.TestCase):
    def context(self, root, count=19):
        assets = []
        for index in range(count):
            name = f"source-{index}.jpg"
            Image.new("RGB", (96, 128), (30 + index * 8 % 180, 60, 120)).save(root / name)
            is_picture = 7 <= index < 15
            asset = {"asset_id": str(uuid4()), "source_name": f"source-{index}", "has_video": True,
                     "mime_type": "image/png" if is_picture else "video/mp4", "duration_seconds": None if is_picture else 12,
                     "_preview_key": name, "_contact_sheet_key": name, "transcript_segments": []}
            if index < 7:
                asset["transcript_segments"] = [{"start": 0, "end": 10, "text": "Talking to camera."}]
            assets.append(asset)
        return {"job": {"edit_style": "high_impact", "recipe": "talking_head"},
                "project": {"privacy_mode": "hybrid"}, "assets": assets}

    def test_all_nineteen_sources_including_late_cutaways_are_pictured_in_four_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = self.context(root)
            before = deepcopy(context)
            content = _model_content(context, SimpleNamespace(media_root=root, editor_max_context_characters=120000))
            images = [item for item in content if item["type"] == "input_image"]
            mapping = " ".join(item["text"] for item in content if item.get("text", "").startswith("Panel-to-source mapping:"))
            self.assertEqual(len(images), 4)
            for asset in context["assets"]:
                self.assertIn(asset["asset_id"], mapping)
            for item in images:
                self.assertEqual(item["detail"], "low")
                with Image.open(io.BytesIO(base64.b64decode(item["image_url"].split(",")[1]))) as decoded:
                    self.assertEqual(decoded.width, 512)
                    self.assertLessEqual(decoded.height, 768)
            self.assertEqual(context, before)
            self.assertIn("Never use a different speaking take", content[0]["text"])

    def test_text_only_mode_reads_no_images(self):
        with tempfile.TemporaryDirectory() as folder:
            context = self.context(Path(folder))
            context["project"]["privacy_mode"] = "text_only"
            with patch("app.editor_visual_context.high_impact_visuals") as pictures:
                content = _model_content(context, SimpleNamespace(editor_max_context_characters=120000))
            pictures.assert_not_called()
            self.assertEqual(len(content), 1)

    def test_missing_early_image_does_not_consume_a_visual_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = self.context(root, 5)
            (root / context["assets"][0]["_preview_key"]).unlink()
            content = high_impact_visuals(context, root)
            images = [item for item in content if item["type"] == "input_image"]
            self.assertEqual(len(images), 4)
            mapping = " ".join(item["text"] for item in content if item.get("text", "").startswith("Panel-to-source mapping:"))
            self.assertIn(context["assets"][-1]["asset_id"], mapping)

    def test_large_inventory_has_explicit_coverage_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = self.context(root, 30)
            content = high_impact_visuals(context, root)
            self.assertIn("24 of 30", content[0]["text"])
            self.assertEqual(sum(item["type"] == "input_image" for item in content), 4)
            self.assertIn("unpictured sources", content[0]["text"])


if __name__ == "__main__":
    unittest.main()
