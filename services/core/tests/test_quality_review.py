import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.edit_plan import MontageEditPlan, TalkingHeadEditPlan
from app.quality_review import parse_render_measurements, review_rendered_video


class QualityReviewTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = str(uuid4())
        self.plan = TalkingHeadEditPlan(schema_version="1.3", recipe="talking_head",
            clips=[{"asset_id": self.asset_id, "source_in": 0, "source_out": 4, "crop": "center_fill"}],
            caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none",
            editorial_summary="Keep this successful story.")
        self.context = {"job": {"music_mode": "none"}, "assets": [{"asset_id": self.asset_id,
            "transcript_segments": [{"start": 0, "end": 4, "text": "A complete spoken thought.",
                "words": [{"start": 0.1, "end": 1.1, "text": "A complete"},
                          {"start": 1.2, "end": 3.9, "text": "spoken thought."}]}]}]}
        self.probe = {"format": {"duration_seconds": 4.05}, "streams": [
            {"type": "video", "width": 540, "height": 960, "color_transfer": "bt709"},
            {"type": "audio"}]}
        self.stderr = '{"input_i":"-15.2","input_tp":"-1.1"}'

    def inspect(self, stderr=None, probe=None, captions=None):
        with patch("app.quality_review.run_command", return_value=SimpleNamespace(stderr=self.stderr if stderr is None else stderr)):
            return review_rendered_video(self.context, self.plan, Path("render.mp4"),
                [{"start": 0, "end": 4, "text": "A complete spoken thought."}] if captions is None else captions,
                width=540, height=960, probe=self.probe if probe is None else probe)

    def test_completed_inspection_is_local_and_preserves_the_edit(self):
        before_plan, before_context = self.plan.model_dump(), deepcopy(self.context)
        report = self.inspect()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["additional_model_tokens"], 0)
        self.assertEqual(report["hosted_model_calls"], 0)
        self.assertEqual(report["automatic_changes"], [])
        self.assertEqual(self.plan.model_dump(), before_plan)
        self.assertEqual(self.context, before_context)
        self.assertEqual(next(c for c in report["checks"] if c["code"] == "story_judgement")["status"], "not_assessed")

    def test_trailing_silence_and_nonfinite_loudness_are_handled(self):
        measured = parse_render_measurements('silence_start: 1.3\n{"input_i":"-inf","input_tp":"-inf"}', 4)
        self.assertEqual(measured["silence_intervals"], [{"start": 1.3, "end": 4}])
        self.assertEqual(measured["loudness"], {})
        json.dumps(measured, allow_nan=False)

    def test_measured_darkness_and_quiet_mix_produce_timestamped_hints(self):
        report = self.inspect('black_start:1 black_end:2 black_duration:1\n'
            'silence_start: 2\nsilence_end: 3.5\n{"input_i":"-29","input_tp":"-0.1"}')
        findings = {finding["code"]: finding for finding in report["findings"]}
        self.assertEqual(findings["quiet_interval"]["clip_index"], 0)
        self.assertEqual(findings["dark_interval"]["start_seconds"], 1)
        self.assertIn("quiet_mix", findings)
        self.assertIn("audio_peak", findings)
        self.assertEqual(report["status"], "attention")

    def test_word_gap_is_a_hint_even_when_music_masks_silence(self):
        self.context["assets"][0]["transcript_segments"][0]["words"][1]["start"] = 3.2
        report = self.inspect()
        gaps = [finding for finding in report["findings"] if finding["code"] == "source_speech_gap"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("not verified silence", gaps[0]["detail"])
        self.assertEqual(gaps[0]["start_seconds"], 1.1)

    def test_speech_cut_and_bad_caption_schedule_are_flagged(self):
        self.plan.clips[0].source_in = 0.5
        report = self.inspect(captions=[{"start": 0, "end": 2}, {"start": 1, "end": 3}])
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("speech_boundary", codes)
        self.assertIn("caption_schedule", codes)

    def test_incorrect_streams_dimensions_duration_and_hdr_are_reported(self):
        self.probe["streams"] = [{"type": "video", "width": 100, "height": 100, "color_transfer": "arib-std-b67"}]
        self.probe["format"]["duration_seconds"] = 2
        report = self.inspect()
        codes = {finding["code"] for finding in report["findings"]}
        self.assertTrue({"streams", "dimensions", "duration", "colour_metadata"} <= codes)

    def test_unknown_colour_is_not_claimed_as_verified(self):
        self.probe["streams"][0].pop("color_transfer")
        report = self.inspect()
        self.assertEqual(report["status"], "incomplete")
        colour = next(c for c in report["checks"] if c["code"] == "colour_metadata")
        self.assertEqual(colour["status"], "unavailable")

    def test_measurement_timeout_preserves_the_preview_and_bounds_processing(self):
        with patch("app.quality_review.run_command", side_effect=subprocess.TimeoutExpired("ffmpeg", 30)) as command:
            report = review_rendered_video(self.context, self.plan, Path("render.mp4"), [{"start": 0, "end": 4}],
                width=540, height=960, probe=self.probe, timeout=7200)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(command.call_args.kwargs["timeout"], 30)
        self.assertIn("-t", command.call_args.args[0])
        self.assertEqual(report["automatic_changes"], [])

    def test_unexpected_source_metadata_failure_is_nonfatal(self):
        self.context["assets"][0]["transcript_segments"] = [None]
        report = review_rendered_video(self.context, self.plan, Path("render.mp4"), [], width=540, height=960)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["additional_model_tokens"], 0)

    def test_requested_music_omission_is_visible(self):
        self.context["job"]["music_mode"] = "present"
        report = self.inspect()
        self.assertTrue(any(f["code"] == "music_selection" for f in report["findings"]))

    def test_missing_captions_for_selected_speech_are_not_a_pass(self):
        report = self.inspect(captions=[])
        self.assertTrue(any(f["code"] == "caption_schedule" for f in report["findings"]))

    def test_muted_montage_does_not_get_dialogue_silence_warnings(self):
        self.plan = MontageEditPlan(schema_version="1.3", recipe="montage", clips=[
            {"asset_id": self.asset_id, "media_kind": "image", "source_in": 0, "source_out": 0,
             "duration": 2, "crop": "center_fill"},
            {"asset_id": self.asset_id, "media_kind": "video", "source_in": 0, "source_out": 2,
             "duration": 2, "crop": "center_fill", "include_source_audio": False}],
            audio_preset="montage_mix_v1", end_card="none", editorial_summary="Quiet visual montage.")
        report = self.inspect('silence_start: 0\nsilence_end: 4\n' + self.stderr)
        self.assertFalse(any(f["code"] in {"quiet_interval", "source_speech_gap"} for f in report["findings"]))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_real_render_is_decoded_without_modifying_the_video(self):
        from app.media_analysis import run_command

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.mp4"
            run_command(["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi", "-i", "testsrc2=s=160x284:r=30:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-color_trc", "bt709", "-colorspace", "bt709", "-color_primaries", "bt709", str(path)], timeout=15)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            self.plan.clips[0].source_out = 2
            self.context["assets"][0]["transcript_segments"] = []
            report = review_rendered_video(self.context, self.plan, path, [], width=160, height=284)
            self.assertIn(report["status"], {"passed", "incomplete"}, report)
            self.assertEqual(next(c for c in report["checks"] if c["code"] == "decode")["status"], "passed")
            self.assertEqual(report["findings"], [])
            self.assertIn("integrated_lufs", report["measurements"]["loudness"])
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
            json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
