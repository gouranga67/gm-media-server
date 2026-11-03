import array
import copy
import math
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
import wave

from app.audio_cleanup import choose_profile, inspect_pcm, measure_source, prepare_voice_cleanup, cleanup_manifest
from app.edit_plan import TalkingHeadEditPlan
from app.edit_renderer import _ffmpeg_filter, _render_video, render_ass
from app.finishing_tools import FinishingTools, clip_voice_cleanup_filter, audio_join_sources, timed_denoise_filter


def pcm_fixture(noise=.012, speech=.16):
    rng = random.Random(32)
    samples = array.array("h")
    for i in range(48000):
        at = i / 16000
        value = rng.uniform(-noise, noise)
        if .5 <= at < 2.5:
            value += speech * math.sin(2 * math.pi * 440 * at)
        samples.append(round(value * 32767))
    return samples.tobytes()


class VoiceCleanupTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = str(uuid4())
        self.asset = dict(asset_id=self.asset_id, _storage_key="source.wav", sha256="a" * 64,
            has_audio=True, duration_seconds=3,
            transcript_segments=[dict(start=.5, end=2.5, text="Recorded words", words=[dict(start=.5, end=2.5, text="Recorded")])])
        self.context = {"job": {}, "project": {"brief": "A product story"}, "assets": [self.asset]}
        self.plan = TalkingHeadEditPlan(schema_version="1.5", recipe="talking_head", caption_style="clean_blue_v1",
            audio_preset="spoken_voice_v1", end_card="none", editorial_summary="Recorded story",
            clips=[dict(asset_id=self.asset_id, source_in=0, source_out=3, crop="center_fill")])

    def test_noisy_signal_gets_gentle_cleanup_but_clean_signal_passes_through(self):
        noisy = inspect_pcm(pcm_fixture(), [(.5, 2.5)])
        decision = choose_profile(self.asset_id, noisy, None)
        self.assertEqual(decision.noise_reduction_db, 6)
        self.assertFalse(decision.compress)
        self.assertEqual(decision.balance_gain_db, 0)
        clean = inspect_pcm(pcm_fixture(noise=.0001), [(.5, 2.5)])
        self.assertEqual(choose_profile(self.asset_id, clean, None).noise_reduction_db, 0)

    def test_missing_speech_irregular_noise_and_low_separation_are_not_denoised(self):
        self.assertEqual(choose_profile(self.asset_id, {}, None).status, "skipped")
        baseline = dict(speech_dbfs=-22, peak_dbfs=-10, noise_dbfs=-39, noise_spread_db=4)
        for changes in [dict(noise_spread_db=14), dict(noise_dbfs=-28)]:
            self.assertEqual(choose_profile(self.asset_id, {**baseline, **changes}, None).noise_reduction_db, 0)
        silence = inspect_pcm(bytes(96000), [(.5, 2.5)])
        self.assertEqual(choose_profile(self.asset_id, silence, None).status, "skipped")

    def test_balance_is_bounded_and_does_not_boost_past_headroom(self):
        quiet = dict(speech_dbfs=-32, peak_dbfs=-14)
        self.assertEqual(choose_profile(self.asset_id, quiet, -22).balance_gain_db, 6)
        self.assertEqual(choose_profile(self.asset_id, {**quiet, "peak_dbfs": -1}, -22).balance_gain_db, 0)
        self.assertEqual(choose_profile(self.asset_id, dict(speech_dbfs=-18, peak_dbfs=-2), -28).balance_gain_db, -6)

    def test_gentle_compression_only_for_large_voice_dynamics_with_high_peaks(self):
        uneven = dict(speech_dbfs=-24, speech_spread_db=18, peak_dbfs=-3)
        self.assertTrue(choose_profile(self.asset_id, uneven, None).compress)
        self.assertFalse(choose_profile(self.asset_id, {**uneven, "peak_dbfs": -15}, None).compress)
        self.assertFalse(choose_profile(self.asset_id, {**uneven, "speech_spread_db": 6}, None).compress)

    def test_existing_saved_mix_is_unchanged_without_opt_in(self):
        with patch("app.audio_cleanup.measure_source") as measure:
            result = prepare_voice_cleanup(self.context, self.plan, SimpleNamespace())
        measure.assert_not_called()
        self.assertIs(result, self.plan)
        self.assertNotIn("voice_cleanup", FinishingTools().model_dump())

    def test_auto_pass_preserves_media_and_other_finishing_and_is_saved(self):
        original = copy.deepcopy(self.plan.model_dump())
        with patch("app.audio_cleanup.measure_source", return_value=inspect_pcm(pcm_fixture(), [(.5, 2.5)])):
            result = prepare_voice_cleanup(self.context, self.plan, SimpleNamespace(), new_edit=True)
        self.assertEqual(result.clips, self.plan.clips)
        self.assertEqual(result.finishing.voice_cleanup, "auto")
        self.assertEqual(cleanup_manifest(result)["hosted_model_calls"], 0)
        restored = TalkingHeadEditPlan.model_validate(result.model_dump(mode="json"))
        self.assertEqual(clip_voice_cleanup_filter(restored, 0), clip_voice_cleanup_filter(result, 0))
        self.assertEqual(self.plan.model_dump(), original)
        self.assertNotIn("atempo", clip_voice_cleanup_filter(restored, 0))
        self.assertNotIn("silenceremove", clip_voice_cleanup_filter(restored, 0))

    def test_whispers_and_preserve_audio_briefs_do_not_auto_opt_in(self):
        for brief in ["An ASMR whisper", "Preserve original audio", "No audio cleanup"]:
            context = {**self.context, "project": {"brief": brief}}
            self.assertIs(prepare_voice_cleanup(context, self.plan, SimpleNamespace(), new_edit=True), self.plan)

    def test_measurement_failure_and_budget_preserve_sources(self):
        with patch("app.audio_cleanup.measure_source", side_effect=subprocess.TimeoutExpired("ffmpeg", 1)):
            result = prepare_voice_cleanup(self.context, self.plan, SimpleNamespace(), new_edit=True)
        self.assertEqual(result.finishing.voice_cleanup_profiles[0].status, "unavailable")
        self.assertEqual(clip_voice_cleanup_filter(result, 0), "")
        with patch("app.audio_cleanup.BUDGET_SECONDS", 0), patch("app.audio_cleanup.measure_source") as measure:
            result = prepare_voice_cleanup(self.context, self.plan, SimpleNamespace(), new_edit=True)
        measure.assert_not_called()
        self.assertEqual(result.finishing.voice_cleanup_profiles[0].status, "unavailable")

    def test_manual_levels_and_denoise_are_not_stacked(self):
        profile = choose_profile(self.asset_id, dict(speech_dbfs=-30, peak_dbfs=-12, noise_dbfs=-44, noise_spread_db=1), -24)
        tools = FinishingTools(voice_cleanup="auto", voice_cleanup_profiles=[profile], voice_denoise=True)
        result = self.plan.model_copy(update={"finishing": tools}, deep=True)
        result.clips[0].source_audio_gain_db = 3
        self.assertEqual(clip_voice_cleanup_filter(result, 0), "")
        result.clips[0].source_audio_gain_db = 0
        result.finishing = FinishingTools.model_validate({**tools.model_dump(), "audio_regions": [dict(start=0, end=1, gain_db=3)]})
        self.assertEqual(clip_voice_cleanup_filter(result, 0), "volume=6.0dB")

    def test_source_cleanup_precedes_music_and_covers_independent_audio_joins(self):
        profile = choose_profile(self.asset_id, inspect_pcm(pcm_fixture(), [(.5, 2.5)]), None)
        result = self.plan.model_copy(update={"finishing": FinishingTools(voice_cleanup="auto", voice_cleanup_profiles=[profile])})
        graph = _ffmpeg_filter(result, Path("empty.ass"), width=180, height=320, frames_per_second=30, music_input_index=1)
        self.assertIn("afftdn=nr=6:", graph.split("[a0]")[0])
        self.assertNotIn("afftdn", next(p for p in graph.split(";") if p.startswith("[1:a:0]")))
        result.finishing = FinishingTools.model_validate({**result.finishing.model_dump(), "audio_joins": [dict(clip_index=0, lead_seconds=0, tail_seconds=0)]})
        joins = audio_join_sources(result, [Path("source.wav")], 1)
        graph = _ffmpeg_filter(result, Path("empty.ass"), width=180, height=320, frames_per_second=30, join_sources=joins)
        self.assertIn("afftdn", next(p for p in graph.split(";") if p.startswith("[1:a:0]")))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_denoise_flushes_first_and_last_speech_without_moving_it(self):
        # A tone up against both boundaries catches a filter that has the right
        # duration but silently delays speech or discards its final 25 ms.
        raw = array.array("h", [round(.16 * math.sin(2 * math.pi * 440 * i / 48000) * 32767) for i in range(48000)])
        output = subprocess.check_output(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", "48000", "-ac", "1", "-i", "pipe:0",
            "-af", timed_denoise_filter(6, -40, 1), "-f", "s16le", "pipe:1"], input=raw.tobytes(), timeout=5)
        self.assertEqual(len(output), len(raw) * 2)
        samples = array.array("h", output)
        for edge in (samples[:960], samples[-960:]):
            self.assertGreater(math.sqrt(sum(float(v) ** 2 for v in edge) / len(edge)) / 32768, .08)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_audio_noise_floor_duration_and_cached_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            pcm = pcm_fixture()
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(pcm)
            settings = SimpleNamespace(media_root=root)
            measured = measure_source(self.asset, 0, 3, settings, 5)
            with patch("app.audio_cleanup.subprocess.run", side_effect=AssertionError("cache should avoid decoding")):
                self.assertEqual(measure_source(self.asset, 0, 3, settings, 5), measured)
            cache = next(root.glob("derived/audio-cleanup/*/*.json"))
            cache.write_text('{"version":"voice_cleanup_v1","speech_dbfs":"invalid"}')
            self.assertEqual(measure_source(self.asset, 0, 3, settings, 5), measured)
            profile = choose_profile(self.asset_id, measured, None)
            result = self.plan.model_copy(update={"finishing": FinishingTools(voice_cleanup="auto", voice_cleanup_profiles=[profile])})
            output = subprocess.check_output(["ffmpeg", "-v", "error", "-nostdin", "-i", str(source),
                "-af", clip_voice_cleanup_filter(result, 0), "-f", "s16le", "-ar", "16000", "pipe:1"], timeout=5)
            cleaned = inspect_pcm(output, [(.5, 2.5)])
            self.assertEqual(len(output), len(pcm))
            self.assertLess(cleaned["noise_dbfs"], measured["noise_dbfs"] - 2)
            self.assertLess(abs(cleaned["speech_dbfs"] - measured["speech_dbfs"]), 2)
            def audible_bounds(raw):
                signal = array.array("h", raw)
                size = 160  # Detect the fixture's tone envelope at 10 ms resolution.
                active = [i / 16000 for i in range(0, len(signal) - size, size)
                    if sum(float(v) ** 2 for v in signal[i:i + size]) / size > (32768 * .05) ** 2]
                return active[0], active[-1]
            for original, treated in zip(audible_bounds(pcm), audible_bounds(output)):
                self.assertLessEqual(abs(treated - original), .010001)
            # Test the actual video path, stream clocks and coverage as well.
            video = root / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=3",
                "-i", str(source), "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(video)], check=True, timeout=10)
            captions = root / "captions.ass"
            captions.write_text(render_ass([], width=180, height=320))
            _render_video([(video, 0, 3)], result, captions, root / "preview.mp4", 20, width=180, height=320)
            probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(root / "preview.mp4")], timeout=5)
            import json
            durations = [float(s["duration"]) for s in json.loads(probe)["streams"]]
            self.assertTrue(all(abs(d - 3) < .05 for d in durations), durations)
