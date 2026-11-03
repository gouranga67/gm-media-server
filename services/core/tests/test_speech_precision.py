import array
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan, protect_spoken_boundaries
from app.edit_renderer import _ffmpeg_filter, _render_video, render_ass
from app.speech_alignment import ctc_spans
from app.speech_precision import (
    VERSION, accept_alignment, align_source, apply_snapshot, boundary_margins,
    backfill_one, normal_word, prepare_context, profile, read_snapshot, windows,
)
from app.speech_join_review import inspect_joins, join_windows


def settings(root):
    return SimpleNamespace(media_root=root, speech_alignment_enabled=True,
        speech_alignment_budget_seconds=5, speech_alignment_edit_budget_seconds=5)


def transcript():
    return {"language": "en", "duration_seconds": 4, "segments": [{"start": 1, "end": 2.2,
        "text": "Cream works.", "words": [
            {"start": 1, "end": 1.4, "text": " Cream", "probability": .9},
            {"start": 1.6, "end": 2.2, "text": " works.", "probability": .95}]}]}


class FakeAligner:
    calls = 0
    def __init__(self, _): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def align(self, source, start, end, words):
        type(self).calls += 1
        table = {"CREAM": (.96, 1.43), "WORKS": (1.58, 2.24)}
        return [dict(start=table[w][0], end=table[w][1], score=.9) for w in words]


class AlignmentLatticeTests(unittest.TestCase):
    def test_ctc_repeated_letters_require_a_blank_and_keep_token_order(self):
        labels = [0, 1, 1, 0, 1, 0, 2, 0]
        emissions = [[math.log(.98 if n == target else .01) for n in range(3)] for target in labels]
        spans = ctc_spans(emissions, [1, 1, 2])
        self.assertEqual([(s[0], s[1]) for s in spans], [(1, 3), (4, 5), (6, 7)])
        self.assertTrue(all(s[2] > .9 for s in spans))
        self.assertIsNone(ctc_spans(emissions[:2], [1, 1]))

    def test_unknown_numbers_and_scripts_are_not_invented_by_alignment(self):
        self.assertEqual(normal_word(" We're! "), "WE'RE")
        self.assertIsNone(normal_word("500ml"))
        self.assertIsNone(normal_word("猫"))
        words = transcript()["segments"][0]["words"]
        for candidates in (None, [], [dict(start=1, end=2, score=.1)] * 2,
                           [dict(start=3, end=3.1, score=.99)] * 2):
            self.assertIsNone(accept_alignment(words, candidates))

    def test_weaker_supported_words_are_explicitly_uncertain(self):
        words = transcript()["segments"][0]["words"]
        result = accept_alignment(words, [dict(start=1, end=1.4, score=.95), dict(start=1.6, end=2.2, score=.5)])
        self.assertEqual(result[0]["timing_source"], "ctc_aligned")
        self.assertEqual(result[1]["timing_source"], "ctc_uncertain")
        self.assertGreater(boundary_margins(result[1], True)[1], boundary_margins(result[0], True)[1])

    def test_long_audio_windows_are_bounded_and_all_supported_words_are_considered(self):
        segments = [{"words": [dict(start=i, end=i + .4, text="word") for i in range(80)]}]
        groups = list(windows(segments))
        self.assertEqual(sum(len(g) for _, g in groups), 80)
        self.assertTrue(all(g[-1][1]["end"] - g[0][1]["start"] <= 10.4 for _, g in groups))

    def test_a_weak_name_between_good_anchors_is_labelled_as_an_estimate(self):
        words = [dict(text=t, start=s, end=e) for t, s, e in
                 [("Our", 1, 1.3), ("brand", 1.4, 1.7), ("works", 1.8, 2.1)]]
        candidates = [dict(start=1.3, end=1.6, score=.95), dict(start=1.4, end=1.7, score=.01),
                      dict(start=2.1, end=2.4, score=.95)]
        result = accept_alignment(words, candidates)
        self.assertEqual([w["text"] for w in result], [w["text"] for w in words])
        self.assertEqual(result[1]["timing_source"], "interpolated")
        self.assertEqual(result[1]["alignment_score"], 0)
        self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(result, result[1:])))
        self.assertEqual(boundary_margins(result[1], True), (.22, .28))
        self.assertIsNone(normal_word("café"))
        self.assertEqual(boundary_margins({"probability": float("nan")}, True), (.22, .28))


class AlignmentCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.settings = settings(self.root)
        self.source = self.root / "source.wav"
        self.source.write_bytes(b"fixture source")
        FakeAligner.calls = 0

    def tearDown(self): self.directory.cleanup()

    def align(self, raw=None, **kwargs):
        return align_source(self.source, raw or transcript(), "a" * 64, self.settings,
                            backend_factory=FakeAligner, **kwargs)

    def test_cached_alignment_preserves_text_and_original_transcript(self):
        raw = transcript(); before = deepcopy(raw)
        key, payload = self.align(raw)
        self.assertEqual(raw, before)
        self.assertEqual(payload["aligned_words"], 2)
        self.assertEqual(payload["segments"][0]["text"], raw["segments"][0]["text"])
        self.assertEqual(payload["segments"][0]["words"][0]["text"], " Cream")
        self.assertEqual(payload["segments"][0]["start"], .96)
        self.assertEqual(payload["segments"][0]["end"], 2.24)
        second, _ = self.align(raw)
        self.assertEqual(key, second)
        self.assertEqual(FakeAligner.calls, 1)

    def test_duplicate_source_content_reuses_alignment_but_new_transcript_invalidates_it(self):
        first, _ = self.align()
        raw = transcript(); raw["segments"][0]["words"][0]["probability"] = .91
        second, _ = self.align(raw)
        self.assertNotEqual(first, second)
        self.assertEqual(read_snapshot(self.settings, first)["segments"][0]["words"][0]["probability"], .9)

    def test_partial_snapshot_stays_immutable_after_background_completion(self):
        key, original = self.align(budget=0)
        self.assertFalse(original["complete"])
        self.assertEqual(FakeAligner.calls, 0)
        new, complete = self.align(resume=True)
        self.assertNotEqual(key, new)
        self.assertEqual(complete["aligned_words"], 2)
        self.assertEqual(read_snapshot(self.settings, key)["aligned_words"], 0)
        context = {"assets": [dict(asset_id="asset", sha256="a" * 64, transcript_segments=transcript()["segments"])]}
        apply_snapshot(context, {"version": VERSION, "assets": {"asset": key}}, self.settings)
        self.assertEqual(context["assets"][0]["transcript_segments"][0]["words"][0]["start"], 1)

    def test_corrupt_window_is_rebuilt_without_changing_a_saved_snapshot(self):
        key, _ = self.align()
        saved = (self.root / key).read_bytes()
        window = next(self.root.glob("analysis/speech-precision/*/*/*/windows/*.json"))
        window.chmod(0o640)
        window.write_text(json.dumps({"words": [{"text": "invented"}]}))
        index = next(self.root.glob("analysis/speech-precision/*/*/*/current.json"))
        index.unlink()
        _, rebuilt = self.align()
        self.assertEqual(FakeAligner.calls, 2)
        self.assertEqual(rebuilt["aligned_words"], 2)
        self.assertEqual((self.root / key).read_bytes(), saved)

    def test_backfill_publishes_a_separate_manifest_and_keeps_original_transcript(self):
        raw_path = self.root / "transcript.json"
        raw_path.write_text(json.dumps(transcript()))
        before = raw_path.read_bytes()
        manifest = {"derived": {"transcript": "transcript.json"}, "manifest_path": "manifest.json"}
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        row = dict(id="asset", sha256="a" * 64, storage_key="source.wav", manifest=manifest)
        database = MagicMock(); database.__enter__.return_value = database
        database.execute.return_value.fetchone.return_value = row
        database.execute.return_value.rowcount = 1
        with patch("app.speech_alignment.LocalAligner", FakeAligner):
            self.assertTrue(backfill_one(self.settings, lambda: database))
        updated = database.execute.call_args.args[1][0].obj
        self.assertEqual(updated["derived"]["speech_precision_profile"], profile(self.settings))
        self.assertEqual(updated["derived"]["speech_precision_summary"]["aligned_words"], 2)
        self.assertEqual(raw_path.read_bytes(), before)
        self.assertNotIn("speech_precision", manifest["derived"])
        self.assertIn("manifest=%s", database.execute.call_args.args[0])

    def test_disabled_backfill_never_queries_database(self):
        self.settings.speech_alignment_enabled = False
        connect = Mock(side_effect=AssertionError("disabled"))
        self.assertFalse(backfill_one(self.settings, connect))

    def test_unavailable_model_does_not_fail_ingest_or_mutate_speech(self):
        engine = Mock(); engine.__enter__ = Mock(side_effect=RuntimeError("model unavailable"))
        key, result = align_source(self.source, transcript(), "a" * 64, self.settings,
                                   backend_factory=lambda _: engine)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["segments"], transcript()["segments"])
        self.assertTrue(result["complete"])

    def test_unknown_language_does_not_load_a_model(self):
        raw = transcript(); raw["language"] = "fr"
        _, result = self.align(raw)
        self.assertEqual(result["status"], "unsupported_language")
        self.assertEqual(FakeAligner.calls, 0)

    def test_disabled_precision_does_no_work_and_legacy_snapshot_changes_nothing(self):
        context = {"assets": [dict(asset_id="a", transcript_segments=transcript()["segments"])]}
        before = deepcopy(context)
        self.settings.speech_alignment_enabled = False
        self.assertEqual(prepare_context(context, self.settings), {})
        apply_snapshot(context, {}, self.settings)
        self.assertEqual(context, before)

    def test_snapshot_rejects_path_escape_or_wrong_source(self):
        with self.assertRaises(ValueError): read_snapshot(self.settings, "../private")
        (self.root / "private.json").write_text(json.dumps({"version": VERSION, "segments": []}))
        with self.assertRaises(ValueError):
            read_snapshot(self.settings, "analysis/speech-precision/../../private.json")
        key, _ = self.align()
        context = {"assets": [dict(asset_id="a", sha256="b" * 64)]}
        with self.assertRaisesRegex(ValueError, "does not match"):
            apply_snapshot(context, {"version": VERSION, "assets": {"a": key}}, self.settings)

    def test_saved_snapshot_detects_overwritten_timing_instead_of_changing_an_approved_edit(self):
        key, payload = self.align()
        path = self.root / key
        path.chmod(0o640)
        payload["segments"][0]["words"][0]["start"] = 1.2
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "invalid speech timing snapshot"):
            read_snapshot(self.settings, key)

    def test_saved_run_uses_its_snapshot_without_loading_the_current_model(self):
        from app.worker import prepare_run_speech_precision
        key, _ = self.align()
        snapshot = {"version": VERSION, "assets": {"a": key}}
        context = {"assets": [dict(asset_id="a", sha256="a" * 64, transcript_segments=[])]}
        database = MagicMock(); database.__enter__.return_value = database
        database.execute.return_value.fetchone.return_value = {"speech_precision_snapshot": snapshot}
        with patch("app.worker.connection", return_value=database), patch("app.worker.get_settings", return_value=self.settings), \
             patch("app.speech_precision.prepare_context", side_effect=AssertionError("must not realign")):
            run = {"edit_plan_id": "saved"}
            prepare_run_speech_precision(context, run)
        self.assertEqual(run["_speech_precision_snapshot"], snapshot)
        self.assertEqual(context["assets"][0]["transcript_segments"][0]["words"][0]["start"], .96)


def make_plan(identity, clips):
    return TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head", clips=[
        dict(asset_id=identity, crop="center_fill", **clip) for clip in clips],
        editorial_summary="Complete recorded speech", caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1", end_card="none")


class SpeechBoundaryTests(unittest.TestCase):
    def test_adaptive_margins_do_not_reintroduce_a_deliberately_excluded_word(self):
        identity = uuid4()
        plan = make_plan(identity, [dict(source_in=1, source_out=2.2)])
        asset = dict(asset_id=str(identity), duration_seconds=4, speech_precision={"version": VERSION},
            transcript_segments=[{"words": [dict(start=.8, end=.95, text="um"),
                dict(start=1, end=1.4, text="cream", probability=.2),
                dict(start=1.6, end=2.2, text="works", probability=.2),
                dict(start=2.3, end=2.5, text="extra")]}])
        protected = protect_spoken_boundaries(plan, [asset])
        self.assertEqual(protected.clips[0].source_in, .95)
        self.assertEqual(protected.clips[0].source_out, 2.3)
        self.assertEqual(plan.clips[0].source_in, 1)

    def test_a_shared_word_is_assigned_to_one_side_instead_of_split(self):
        identity = uuid4()
        plan = make_plan(identity, [dict(source_in=1, source_out=1.65), dict(source_in=1.75, source_out=2.5)])
        asset = dict(asset_id=str(identity), duration_seconds=4, speech_precision={"version": VERSION},
            transcript_segments=[{"words": [dict(start=1.5, end=1.9, text="shared"), dict(start=2, end=2.3, text="word")]}])
        protected = protect_spoken_boundaries(plan, [asset])
        self.assertEqual(protected.clips[0].source_out, protected.clips[1].source_in)
        self.assertIn(protected.clips[0].source_out, (1.5, 1.9))
        asset.pop("speech_precision")
        legacy = protect_spoken_boundaries(plan, [asset])
        self.assertEqual(legacy.clips[0].source_out, 1.7)

    def test_visual_dip_does_not_apply_a_long_fade_over_refined_speech(self):
        identity = uuid4()
        plan = make_plan(identity, [dict(source_in=0, source_out=1), dict(source_in=1, source_out=2, transition="dip_to_black")])
        graph = _ffmpeg_filter(plan, Path("empty.ass"), width=160, height=284, frames_per_second=30, safe_speech_joins=True)
        self.assertIn("fade=t=in:st=0:d=0.180", graph)
        self.assertIn("afade=t=out:st=0.995:d=0.005", graph)
        self.assertNotIn("afade=t=in:st=0:d=0.180", graph)

    def test_rendered_join_flags_are_advisory_and_bounded(self):
        identity = uuid4()
        plan = make_plan(identity, [dict(source_in=0, source_out=1), dict(source_in=1, source_out=2)])
        context = {"assets": [dict(asset_id=str(identity), transcript_segments=[{"words": [
            dict(start=.1, end=1, text="one"), dict(start=1, end=1.9, text="two")]}])]}
        raw = array.array("f", [.1] * 16000).tobytes()
        with patch("app.speech_join_review.subprocess.run", return_value=SimpleNamespace(stdout=raw)) as decode:
            report = inspect_joins(context, plan, Path("fixture.mp4"))
        self.assertEqual(report["status"], "attention")
        self.assertTrue(report["joins"][0]["review"])
        self.assertEqual(decode.call_args.kwargs["timeout"], 4)
        self.assertEqual(plan.clips[0].source_out, 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_speech_audio_survives_picture_dips_until_the_join(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source.mkv"; output = root / "finished.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=160x284:r=30:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                "-c:v", "libx264", "-c:a", "pcm_s16le", str(source)], check=True, capture_output=True, timeout=15)
            plan = make_plan(uuid4(), [dict(source_in=0, source_out=1), dict(source_in=1, source_out=2, transition="dip_to_black")])
            ass = root / "empty.ass"; ass.write_text(render_ass([], width=160, height=284))
            _render_video([(source, 0, 1), (source, 1, 2)], plan, ass, output, 30,
                width=160, height=284, safe_speech_joins=True)
            raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1",
                "-ar", "8000", "-f", "f32le", "-"], timeout=10)
            samples = array.array("f", raw)
            def rms(at):
                values = samples[round(at * 8000):round((at + .04) * 8000)]
                return math.sqrt(sum(v*v for v in values) / len(values))
            self.assertGreater(rms(.93) / rms(.5), .9)


class SpeechProgressTests(unittest.TestCase):
    def test_hosted_planner_keeps_refined_times_without_alignment_provenance(self):
        from app.editor_provider import _public_context
        context = {"job": {}, "speech_precision": {"version": VERSION}, "assets": [
            dict(asset_id="a", speech_precision={"aligned_words": 2}, transcript_segments=[
                {"start": .96, "end": 2.24, "text": "Cream works", "words": [
                    dict(start=.96, end=1.43, text="Cream", timing_source="ctc_aligned")] }]) ]}
        before = deepcopy(context)
        public = _public_context(context, 10000)
        self.assertNotIn("speech_precision", public)
        self.assertNotIn("speech_precision", public["assets"][0])
        self.assertNotIn("words", public["assets"][0]["transcript_segments"][0])
        self.assertEqual(public["assets"][0]["transcript_segments"][0]["end"], 2.24)
        self.assertEqual(context, before)

    def test_background_alignment_waits_for_editing_and_indexing_work(self):
        from app import worker
        tasks = ["catalog_one_asset", "process_one_edit", "process_one_final_export", "process_one_delivery_variant",
                 "process_one_concept", "process_one_organization", "process_one_post", "process_one_caption",
                 "analyze_one_asset", "process_one_music_track", "index_one_asset_visually", "finalize_one_upload"]
        maintenance = ["seed_pending_ingests", "seed_pending_catalogs", "recover_interrupted_concepts",
                       "recover_interrupted_organization", "recover_interrupted_publishing", "seed_pending_visual_indexes"]
        with tempfile.TemporaryDirectory() as directory:
            for active in ("process_one_edit", "index_one_asset_visually", None):
                mocks = {name: Mock(return_value=name == active) for name in tasks}
                mocks.update({name: Mock() for name in maintenance})
                mocks["get_settings"] = Mock(return_value=settings(Path(directory)))
                with patch.multiple(worker, **mocks), patch("app.speech_precision.backfill_one", return_value=True) as backfill:
                    worker.run_work_cycle(worker.WorkerState())
                self.assertEqual(backfill.call_count, int(active is None))

    def test_progress_reports_coverage_and_unavailable_sources_without_model_calls(self):
        from app.speech_status import speech_precision_status
        conf = settings(Path("/unused"))
        database = MagicMock(); database.__enter__.return_value = database
        database.execute.return_value.fetchall.return_value = [
            dict(profile=profile(conf), summary=dict(status="partial", total_words=12, aligned_words=5,
                uncertain_words=3, interpolated_words=2)),
            dict(profile=profile(conf), summary=dict(status="unavailable", total_words=10)),
            dict(profile=None, summary=None)]
        with patch("app.speech_alignment.LocalAligner", side_effect=AssertionError("read only")):
            info = speech_precision_status(conf, lambda: database)
        self.assertEqual(info["pending_sources"], 1)
        self.assertEqual(info["aligned_words"], 5)
        self.assertEqual(info["interpolated_words"], 2)
        self.assertEqual(info["source_statuses"]["unavailable"], 1)
        self.assertEqual(info["status"], "backfilling")
        self.assertTrue(info["read_only"])
        self.assertEqual(info["hosted_model_calls"], 0)
