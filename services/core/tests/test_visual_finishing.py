import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan, apply_timeline_adjustments, schema_for_recipe, derive_duration_variant
from app.finishing_tools import FinishingTools, validate_finishing
from app.visual_finishing import face_track, prepare_visual_finishing, source_crop_filter, visual_manifest, measure_clip, _valid
from app.finishing_renderer import caption_safe_card_layout, position_broll_cards
from app.edit_renderer import _render_video, render_ass
from app.media_analysis import run_command


def fixture(clips=1, **tools):
    assets = [dict(asset_id=str(uuid4()), has_audio=True, has_video=True, duration_seconds=30, _storage_key=f"source{i}.mp4") for i in range(clips)]
    plan = TalkingHeadEditPlan(schema_version="1.5", recipe="talking_head", caption_style="clean_blue_v1", audio_preset="spoken_voice_v1",
        end_card="none", editorial_summary="Preserve the recorded explanation.", finishing=FinishingTools(**tools),
        clips=[dict(asset_id=a["asset_id"], source_in=0, source_out=3, crop="center_fill") for a in assets])
    return {"job": {"output_aspect": "vertical"}, "assets": assets}, plan


def measured(level=.4, x=.7):
    return dict(version="selected_visual_v1", width=640, height=360, hdr=False,
        frames=[dict(time=i / 2, luma=level, highlight=.8, faces=[dict(x=x + i * .005, y=.4, width=.08, height=.14)]) for i in range(6)])


class VisualFinishingTests(unittest.TestCase):
    def test_defaults_and_old_hash_contract_do_not_gain_new_fields(self):
        value = FinishingTools().model_dump(mode="json")
        for key in ("smart_framing", "shot_match", "safe_overlays", "visual_profiles"):
            self.assertNotIn(key, value)
        self.assertEqual(FinishingTools.model_validate(value).model_dump(mode="json"), value)

    def test_optional_local_fields_do_not_inflate_hosted_editor_schema(self):
        for recipe in ("talking_head", "montage"):
            schema = json.dumps(schema_for_recipe(recipe))
            self.assertNotIn("visual_profiles", schema)
            self.assertNotIn("FacePoint", schema)
            self.assertNotIn("smart_framing", schema)

    def test_no_inspection_without_explicit_opt_in(self):
        context, plan = fixture()
        with patch("app.visual_finishing.measure_clip") as measure:
            self.assertIs(prepare_visual_finishing(context, plan), plan)
        measure.assert_not_called()

    def test_sparse_continuous_single_face_is_accepted_but_not_identity(self):
        points, note = face_track(measured(), 3)
        self.assertEqual(len(points), 6)
        self.assertIn("Sparse", note)
        context, plan = fixture(smart_framing="face")
        before = plan.model_dump(mode="json")
        with patch("app.visual_finishing.measure_clip", return_value=measured()):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        after = result.model_dump(mode="json")
        self.assertEqual(after["clips"], before["clips"])
        self.assertEqual(after["music_mix"], before["music_mix"])
        self.assertEqual(len(result.finishing.visual_profiles[0].points), 6)
        self.assertFalse(visual_manifest(result)["identity_recognition"])
        validate_finishing(result, context["assets"])
        with patch("app.visual_finishing.measure_clip") as measure:
            self.assertIs(prepare_visual_finishing(context, result), result)
        measure.assert_not_called()

    def test_group_missing_faces_hard_jump_and_uninspected_tail_decline(self):
        cases = []
        group = measured(); group["frames"][2]["faces"] *= 2; cases.append((group, 3))
        missing = measured(); missing["frames"][1]["faces"] = []; missing["frames"][2]["faces"] = []; cases.append((missing, 3))
        jump = measured(); jump["frames"][3]["faces"][0]["x"] = .2; cases.append((jump, 3))
        cases.append((measured(), 5))
        edge = measured(x=.02); cases.append((edge, 3))
        for sample, duration in cases:
            with self.subTest(sample=sample, duration=duration):
                self.assertEqual(face_track(sample, duration)[0], [])

    def test_long_clips_stills_and_inspection_timeout_keep_picture(self):
        context, plan = fixture(smart_framing="face")
        long = plan.model_copy(update={"clips": [plan.clips[0].model_copy(update={"source_out": 20})]})
        with patch("app.visual_finishing.measure_clip") as measure:
            result = prepare_visual_finishing(context, long, SimpleNamespace())
        measure.assert_not_called()
        self.assertEqual(result.finishing.visual_profiles[0].status, "skipped")
        with patch("app.visual_finishing.measure_clip", side_effect=subprocess.TimeoutExpired("inspect", 5)):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual(result.finishing.visual_profiles[0].status, "unavailable")
        self.assertEqual(source_crop_filter(result, 0, 180, 320), "")
        still = MontageEditPlan(schema_version="1.5", recipe="montage", audio_preset="montage_mix_v1", end_card="none",
            editorial_summary="Preserve still", clips=[dict(asset_id=context["assets"][0]["asset_id"], media_kind="image", source_in=0, source_out=0, duration=3, crop="center_fill")] * 2,
            finishing=FinishingTools(smart_framing="face"))
        with patch("app.visual_finishing.measure_clip") as measure:
            result = prepare_visual_finishing(context, still, SimpleNamespace())
        measure.assert_not_called()
        self.assertEqual(result.finishing.visual_profiles[0].status, "skipped")

    def test_eight_clip_and_wall_time_budgets_are_enforced(self):
        context, plan = fixture(10, smart_framing="face")
        with patch("app.visual_finishing.measure_clip", return_value=measured()) as measure:
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual(measure.call_count, 8)
        self.assertEqual(sum(p.status == "unavailable" for p in result.finishing.visual_profiles), 2)
        with patch("app.visual_finishing.time.monotonic", side_effect=[0, 21, 21, 21, 21, 21, 21, 21, 21, 21, 21]), patch("app.visual_finishing.measure_clip") as measure:
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        measure.assert_not_called()

    def test_profile_cannot_attach_to_another_clip_and_trim_invalidates_it(self):
        context, plan = fixture(smart_framing="face")
        with patch("app.visual_finishing.measure_clip", return_value=measured()):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        broken = result.model_copy(update={"clips": [result.clips[0].model_copy(update={"source_in": .1})]})
        with self.assertRaisesRegex(ValueError, "source range"):
            validate_finishing(broken, context["assets"])
        trimmed = apply_timeline_adjustments(result, [dict(clip_index=0, source_in=.2, source_out=2.8)], context["assets"])
        self.assertEqual(trimmed.finishing.visual_profiles, [])
        self.assertEqual(trimmed.finishing.smart_framing, "face")

    def test_manual_camera_priority_and_crop_fit_gate(self):
        context, plan = fixture(smart_framing="face", motions=[dict(clip_index=0, points=[dict(time=0, zoom=1.2)])])
        with patch("app.visual_finishing.measure_clip", return_value=measured()):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual(source_crop_filter(result, 0, 180, 320), "")
        self.assertIn("Manual", result.finishing.visual_profiles[0].note)
        huge = measured()
        for frame in huge["frames"]:
            frame["faces"][0].update(width=.4, x=.5)
        context, plan = fixture(smart_framing="face")
        with patch("app.visual_finishing.measure_clip", return_value=huge):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertFalse(result.finishing.visual_profiles[0].points)

    def test_exposure_is_bounded_and_manual_hdr_highlights_take_priority(self):
        context, plan = fixture(2, shot_match=True)
        samples = [measured(.3), measured(.4)]
        with patch("app.visual_finishing.measure_clip", side_effect=samples):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual([p.brightness for p in result.finishing.visual_profiles], [.035, -.035])
        plan.finishing = FinishingTools(shot_match=True, colours=[dict(clip_index=0)])
        with patch("app.visual_finishing.measure_clip", side_effect=samples):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual(result.finishing.visual_profiles[0].brightness, 0)
        samples[0]["hdr"] = True
        with patch("app.visual_finishing.measure_clip", side_effect=samples):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertTrue(all(p.brightness == 0 for p in result.finishing.visual_profiles))
        samples[0]["hdr"] = False
        for frame in samples[0]["frames"]:
            frame["highlight"] = .99
        plan.finishing = FinishingTools(shot_match=True)
        with patch("app.visual_finishing.measure_clip", side_effect=samples):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertEqual(result.finishing.visual_profiles[0].brightness, 0)

    def test_corrupt_cache_is_not_trusted(self):
        self.assertTrue(_valid(measured(), 3))
        for field, value in (("luma", float("nan")), ("time", 20), ("faces", [dict(x=2, y=.5, width=.1, height=.1)])):
            bad = measured(); bad["frames"][0][field] = value
            self.assertFalse(_valid(bad, 3))

    def test_a_tighter_delivery_crop_can_decline_a_saved_face_path(self):
        context, plan = fixture(smart_framing="face")
        context["job"]["output_aspect"] = "landscape"
        sample = measured()
        for frame in sample["frames"]:
            frame["faces"][0].update(x=.5, width=.4, height=.15)
        with patch("app.visual_finishing.measure_clip", return_value=sample):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        self.assertTrue(result.finishing.visual_profiles[0].points)
        self.assertTrue(source_crop_filter(result, 0, 640, 360))
        self.assertEqual(source_crop_filter(result, 0, 180, 320), "")
        report = visual_manifest(result, "vertical")
        self.assertFalse(report["profiles"][0]["framing_applied"])
        self.assertIn("not used", report["profiles"][0]["note"])

    def test_duration_variant_replays_frozen_profiles_as_a_prefix_without_reinspection(self):
        context, plan = fixture(2, smart_framing="face", shot_match=True)
        with patch("app.visual_finishing.measure_clip", side_effect=[measured(.3), measured(.4)]):
            result = prepare_visual_finishing(context, plan, SimpleNamespace())
        with patch("app.visual_finishing.measure_clip", side_effect=AssertionError("approved prefix must not be inspected")):
            variant = derive_duration_variant(result, 4)
        self.assertEqual(variant.finishing.visual_profiles[0], result.finishing.visual_profiles[0])
        second = variant.finishing.visual_profiles[1]
        self.assertEqual(second.source_out, 1)
        self.assertTrue(all(p.time <= 1 for p in second.points))
        self.assertEqual(second.brightness, result.finishing.visual_profiles[1].brightness)
        validate_finishing(variant, context["assets"])

    def test_callout_yields_when_all_caption_bands_are_occupied(self):
        from app.creative_treatments import treatment_events
        tools = FinishingTools(safe_overlays=True, callouts=[dict(start=0, end=2, text="Proof")])
        captions = [dict(start=0, end=.5, position="upper"), dict(start=.5, end=1, position="middle"), dict(start=1, end=2, position="lower_safe")]
        self.assertEqual(treatment_events(tools, 540, 960, captions), "")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_inspection_timeout_reaps_its_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "source0.mp4").write_bytes(b"synthetic unusable source")
            context, plan = fixture(smart_framing="face")
            with self.assertRaises(subprocess.TimeoutExpired):
                measure_clip(context["assets"][0], plan.clips[0], SimpleNamespace(media_root=root), .000001)

    def test_image_card_uses_actual_timed_captions_without_moving_speech(self):
        context, plan = fixture(safe_overlays=True)
        from app.edit_plan import BrollCue
        cue = BrollCue(asset_id=uuid4(), media_kind="image", source_in=0, source_out=0, start_seconds=.5, duration_seconds=1, editorial_intent="Show proof")
        sources = [dict(cue=cue)]
        position_broll_cards(sources, [dict(start=0, end=1, position="upper"), dict(start=1, end=2, position="lower_safe"), dict(start=2, end=3, position="middle")], plan)
        self.assertEqual(sources[0]["caption_bands"], ["lower_safe", "upper"])
        for w, h in ((180, 320), (540, 960), (1920, 1080)):
            box = caption_safe_card_layout(w, h, sources[0]["caption_bands"])
            self.assertGreater(box["center_y"] - box["max_height"] / 2, h * .32)
            self.assertLess(box["center_y"] + box["max_height"] / 2, h * .61)
        self.assertEqual(plan.clips[0].source_out, 3)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_render_follows_original_picture_before_crop_and_preserves_audio(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, caption = root / "source.mp4", root / "captions.ass"
            # A red/green timed marker at the position of the measured face. At the
            # beginning it lies outside the old centre crop of a 16:9 source.
            run_command(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=0x203080:s=640x360:r=60:d=3",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-vf",
                "drawbox=x=450:y=120:w=50:h=50:color=red:t=fill:enable='lt(t,1.5)',drawbox=x=450:y=120:w=50:h=50:color=lime:t=fill:enable='gte(t,1.5)'", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], timeout=15)
            context, plan = fixture(smart_framing="face")
            sample = measured(x=.74)
            for frame in sample["frames"]:
                frame["faces"][0].update(x=.74, y=.4)
            with patch("app.visual_finishing.measure_clip", return_value=sample):
                tracked = prepare_visual_finishing(context, plan, SimpleNamespace())
            caption.write_text(render_ass([], width=180, height=320))
            base, final = root / "base.mp4", root / "final.mp4"
            _render_video([(source, 0, 3)], plan, caption, base, 30, width=180, height=320)
            _render_video([(source, 0, 3)], tracked, caption, final, 30, width=180, height=320)
            def decode(path, at):
                data = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
                return Image.frombytes("RGB", (180, 320), data)
            def reds(im):
                return sum(r > 180 and g < 70 and b < 70 for r, g, b in im.getdata())
            self.assertLess(reds(decode(base, .25)), 10)
            self.assertGreater(reds(decode(final, .25)), 800)
            late = decode(final, 2.5)
            self.assertLess(reds(late), 10)
            self.assertGreater(sum(g > 180 and r < 70 and b < 70 for r, g, b in late.getdata()), 800)
            def audio(path):
                return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-"])
            self.assertEqual(audio(base), audio(final))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_inspection_and_cache_reuse_do_not_require_hosted_models(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("Worker OpenCV dependency required")
        from app.visual_finishing import MODEL_PATH
        if not Path(os.environ.get("VISUAL_FRAMING_MODEL_PATH", MODEL_PATH)).is_file():
            self.skipTest("Pinned worker face detector required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source0.mp4"
            run_command(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=0x405060:s=640x360:r=30:d=3", "-c:v", "libx264", "-preset", "ultrafast", str(source)], timeout=15)
            context, plan = fixture(smart_framing="face")
            settings = SimpleNamespace(media_root=root)
            value = measure_clip(context["assets"][0], plan.clips[0], settings, 5)
            self.assertEqual(len(value["frames"]), 6)
            self.assertTrue(all(not f["faces"] for f in value["frames"]))
            with patch("app.visual_finishing.subprocess.Popen", side_effect=AssertionError("must reuse cache")):
                self.assertEqual(measure_clip(context["assets"][0], plan.clips[0], settings, 5), value)
