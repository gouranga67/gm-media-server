"""Reject truncated muxes and verify actual frames/speech across mixed joins."""

import array
import math
import runpy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan
from app.edit_renderer import _render_video, render_ass
from app.montage_renderer import _render
from app.media_analysis import probe_media
from app.render_integrity import render_timing_error
from test_camera_timing import COLOURS, WIDTH, HEIGHT, decode_video, make_source


class RenderIntegrityTests(unittest.TestCase):
    def test_each_track_must_cover_the_edit_even_if_the_container_does(self):
        good = {"format": {"duration_seconds": 32.68}, "streams": [
            {"type": "video", "duration_seconds": 32.666667, "start_seconds": 0},
            {"type": "audio", "duration_seconds": 32.68, "start_seconds": 0}]}
        self.assertIsNone(render_timing_error(good, 32.68))
        for kind in ("video", "audio"):
            with self.subTest(kind=kind):
                broken = {"format": good["format"], "streams": [dict(s) for s in good["streams"]]}
                next(s for s in broken["streams"] if s["type"] == kind)["duration_seconds"] = 16.833
                self.assertIn(kind + " is", render_timing_error(broken, 32.68))
        for value in (None, float("nan"), float("inf"), 0):
            good["streams"][0]["duration_seconds"] = value
            self.assertIsNotNone(render_timing_error(good, 32.68))
        good["streams"][0].update(duration_seconds=32.68, start_seconds=0.5)
        self.assertIn("start", render_timing_error(good, 32.68))

    def test_successful_ffmpeg_exit_cannot_replace_a_good_file_with_a_short_track(self):
        for recipe in ("talking_head", "montage"):
            with self.subTest(recipe=recipe), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "existing.mp4"
                output.write_bytes(b"previous usable render")
                asset_id = str(uuid4())
                clip = dict(asset_id=asset_id, source_in=0, source_out=4, crop="center_fill")
                document = dict(schema_version="1.4", recipe=recipe, clips=[clip],
                    caption_style="clean_blue_v1", end_card="none", editorial_summary="Saved cut")
                if recipe == "talking_head":
                    document["audio_preset"] = "spoken_voice_v1"
                    plan = TalkingHeadEditPlan.model_validate(document)
                    module = "app.edit_renderer"
                else:
                    document["audio_preset"] = "montage_mix_v1"
                    document.pop("caption_style")
                    clip.update(source_out=2, media_kind="video", duration=2, include_source_audio=True)
                    document["clips"].append(dict(clip))
                    plan = MontageEditPlan.model_validate(document)
                    module = "app.montage_renderer"

                def fake_encode(command, **kwargs):
                    Path(command[-1]).write_bytes(b"truncated but nonempty")
                    return SimpleNamespace(returncode=0, stderr="")

                def probe(path, timeout):
                    return {"streams": [{"type": "video", "duration_seconds": 2},
                                         {"type": "audio", "duration_seconds": 4}]}

                with patch(module + ".run_command", side_effect=fake_encode), \
                     patch(module + ".probe_media", side_effect=probe), \
                     patch("app.montage_renderer._render_source", return_value=root / "source.mp4"):
                    with self.assertRaisesRegex(RuntimeError, "video is 2.000s; expected 4.000s"):
                        if recipe == "talking_head":
                            _render_video([(root / "source.mp4", 0, 4)], plan,
                                root / "captions.ass", output, 10)
                        else:
                            _render({"assets": [{"asset_id": asset_id, "has_audio": True}],
                                     "creative_effect_library": []}, plan, output,
                                width=WIDTH, height=HEIGHT, final=False,
                                settings=SimpleNamespace(analysis_command_timeout_seconds=10))
                self.assertEqual(output.read_bytes(), b"previous usable render")
                self.assertFalse((root / ".existing.part.mp4").exists())


class SavedCutRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[3] / "scripts" / "rebuild-previews.py"
        cls.script = runpy.run_path(str(path))

    def test_old_deployment_cannot_queue_a_rebuild(self):
        from unittest.mock import Mock
        request = Mock(return_value={"build_id": "old"})
        with self.assertRaisesRegex(RuntimeError, "deploy the timing fix"):
            self.script["rebuild"]("job", request)
        self.assertEqual(request.call_count, 1)

    def test_recovery_uses_only_saved_plan_endpoint_and_keeps_older_versions(self):
        from unittest.mock import Mock
        previous = dict(id="original", version=1, status="ready", manifest={"edit_plan_sha256": "same"})
        current = dict(id="rebuild", version=2, status="ready", manifest={"edit_plan_sha256": "same",
            "render": {"timing_pipeline": self.script["TIMING_PIPELINE"], "stream_timing_verified": True}})
        request = Mock(side_effect=[{"render_timing_pipeline": self.script["TIMING_PIPELINE"]},
            {"latest_run": previous}, {"id": "rebuild", "version": 2}, {"versions": [current, previous]}])
        self.assertEqual(self.script["rebuild"]("job", request), current)
        mutations = [c for c in request.call_args_list if c.kwargs.get("method") == "POST"]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0].args[0], "jobs/job/preview/rebuild")
        self.assertEqual(previous["version"], 1)

    def test_recovery_never_claims_a_different_cut_is_an_exact_rebuild(self):
        from unittest.mock import Mock
        previous = dict(id="original", version=1, status="ready", manifest={"edit_plan_sha256": "before"})
        current = dict(id="rebuild", version=2, status="ready", manifest={"edit_plan_sha256": "different"})
        request = Mock(side_effect=[{"render_timing_pipeline": self.script["TIMING_PIPELINE"]},
            {"latest_run": previous}, {"id": "rebuild", "version": 2}, {"versions": [current, previous]}])
        with self.assertRaisesRegex(RuntimeError, "differs from the previous plan"):
            self.script["rebuild"]("job", request)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class MixedJoinTimingTests(unittest.TestCase):
    def test_fractional_cuts_and_dissolves_keep_later_picture_and_speech_in_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for rate in (30, 60):
                path = root / f"source-{rate}.mkv"
                make_source(path, rate, audio_offset=0.09)
                sources.append(path)
            captions = root / "empty.ass"
            captions.write_text(render_ass([], width=WIDTH, height=HEIGHT))
            durations = [0.91, 1.10, 1.46, 0.77, 1.08, 1.77, 1.29, 0.94, 1.36]
            for recipe in ("talking_head", "montage"):
                for dissolves in (False, True):
                    with self.subTest(recipe=recipe, dissolves=dissolves):
                        clips, paths = [], {}
                        for index, duration in enumerate(durations):
                            asset_id = str(uuid4())
                            start = 0.13 if index % 2 else 0.37
                            clip = dict(asset_id=asset_id, source_in=start, source_out=start + duration,
                                crop="center_fill", visual_preset="punch_in" if index % 2 else "standard",
                                transition="cross_dissolve" if dissolves and index in (3, 5, 7) else "cut")
                            if recipe == "montage":
                                clip.update(media_kind="video", duration=duration, include_source_audio=True)
                            clips.append(clip)
                            paths[asset_id] = sources[index % 2]
                        document = dict(schema_version="1.4", recipe=recipe, clips=clips,
                            end_card="none", editorial_summary="Mixed-rate joins preserve source timing.",
                            caption_style="clean_blue_v1",
                            audio_preset="spoken_voice_v1" if recipe == "talking_head" else "montage_mix_v1")
                        model = TalkingHeadEditPlan if recipe == "talking_head" else MontageEditPlan
                        if recipe == "montage":
                            document.pop("caption_style")
                        plan = model.model_validate(document)
                        before = plan.model_dump(mode="json")
                        output = root / f"{recipe}-{dissolves}.mp4"
                        if recipe == "talking_head":
                            _render_video([(paths[str(c.asset_id)], c.source_in, c.source_out) for c in plan.clips],
                                plan, captions, output, 30, width=WIDTH, height=HEIGHT)
                        else:
                            with patch("app.montage_renderer._render_source",
                                       side_effect=lambda settings, asset, **kw: paths[asset["asset_id"]]):
                                _render({"assets": [{"asset_id": aid, "has_audio": True} for aid in paths],
                                         "creative_effect_library": []}, plan, output,
                                    width=WIDTH, height=HEIGHT, final=False,
                                    settings=SimpleNamespace(analysis_command_timeout_seconds=30), captions_path=captions)
                        self.assertEqual(before, plan.model_dump(mode="json"))
                        probe = probe_media(output, 10)
                        for stream in probe["streams"]:
                            self.assertAlmostEqual(stream["duration_seconds"], sum(durations), delta=0.055)
                        pixels = decode_video(output)
                        frame_bytes = WIDTH * HEIGHT * 3
                        self.assertAlmostEqual(len(pixels) / frame_bytes, round(sum(durations) * 30), delta=1)
                        pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output),
                            "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], timeout=20)
                        audio = array.array("f", pcm)

                        def rms(at):
                            samples = audio[round(at * 48000):round((at + 0.025) * 48000)]
                            return math.sqrt(sum(s * s for s in samples) / len(samples))

                        elapsed = 0.0
                        for index, (clip, duration) in enumerate(zip(clips, durations)):
                            # Check real moving colour markers after every join, including
                            # the last clip. Padding one frozen frame to length cannot pass.
                            for local in (0.30, 0.65):
                                frame_index = round((elapsed + local) * 30)
                                source_time = clip["source_in"] + frame_index / 30 - elapsed
                                if min(source_time % 0.5, 0.5 - source_time % 0.5) < 0.08:
                                    continue
                                expected = COLOURS[int(source_time * 2)]
                                offset = frame_index * frame_bytes + (HEIGHT // 2 * WIDTH + WIDTH // 2) * 3
                                actual = tuple(pixels[offset:offset + 3])
                                self.assertTrue(all(abs(a - b) < 45 for a, b in zip(actual, expected)),
                                    (recipe, dissolves, index, local, actual, expected))
                            # Each source has a known 90ms audio lead-in. Preserve it,
                            # rather than shifting speech earlier again at each cut.
                            pulse = elapsed + 0.5 + 0.09 - clip["source_in"] + 0.05
                            self.assertGreater(rms(pulse), rms(pulse + 0.20) * 3,
                                (recipe, dissolves, index, pulse))
                            elapsed += duration
