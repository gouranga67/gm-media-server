import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.edit_plan import (CreativeEffectCue, EDIT_PLAN_JSON_SCHEMA, TalkingHeadEditPlan, apply_timeline_adjustments,
    derive_duration_variant, repair_predictable_plan_defaults, validate_edit_plan)
from app.edit_renderer import _render_video, render_ass
from app.finishing_renderer import append_broll_filters, rhythmic_zoom, selected_broll
from app.config import Settings
from app.editor_provider import _model_content
from app.media_analysis import run_command
from app.schemas import JobCreate, RevisionCreate


class HighImpactTests(unittest.TestCase):
    def setUp(self):
        self.voice, self.cover, self.image = [str(uuid4()) for _ in range(3)]
        self.assets = [{"asset_id": self.voice, "has_video": True, "has_audio": True, "duration_seconds": 12},
                       {"asset_id": self.cover, "has_video": True, "has_audio": True, "duration_seconds": 8},
                       {"asset_id": self.image, "mime_type": "image/jpeg"}]
        self.doc = {"schema_version": "1.4", "recipe": "talking_head",
            "clips": [{"asset_id": self.voice, "source_in": 0, "source_out": 10, "crop": "center_fill", "visual_preset": "rhythmic_punch"}],
            "caption_style": "clean_blue_v1", "audio_preset": "spoken_voice_v1", "end_card": "none",
            "editorial_summary": "A complete spoken story.", "broll": [{"asset_id": self.cover, "media_kind": "video",
                "source_in": 1, "source_out": 3, "start_seconds": 2, "duration_seconds": 2,
                "editorial_intent": "Show the uploaded product close-up during the explanation."}]}
        self.direction = {"edit_style": "high_impact"}

    def validate(self):
        return validate_edit_plan(self.doc, self.assets, creative_direction=self.direction)

    def test_high_impact_and_overlay_controls_are_opt_in(self):
        self.assertEqual(JobCreate().edit_style, "energetic")
        self.assertEqual(JobCreate(edit_style="high_impact").edit_style, "high_impact")
        self.assertFalse(RevisionCreate(broll_enabled=False).broll_enabled)
        self.direction["edit_style"] = "clean"
        with self.assertRaisesRegex(ValueError, "High impact"):
            self.validate()

    def test_broll_does_not_recut_dialogue(self):
        before = deepcopy(self.doc)
        plan = self.validate()
        self.assertEqual([(c.source_in, c.source_out) for c in plan.clips], [(0, 10)])
        self.assertEqual(len(plan.broll), 1)
        self.assertEqual(before, self.doc)
        self.assertIn("broll", EDIT_PLAN_JSON_SCHEMA["required"])

    def test_images_can_cover_speech_without_image_audio(self):
        self.doc["broll"][0].update(asset_id=self.image, media_kind="image", source_in=0, source_out=0)
        self.assertEqual(self.validate().broll[0].media_kind, "image")

    def test_broll_rejects_unowned_out_of_range_and_invalid_media(self):
        cases = [({"asset_id": str(uuid4())}, "does not belong"),
                 ({"source_in": 7, "source_out": 9}, "exceeds"),
                 ({"source_out": 4}, "duration must match"),
                 ({"start_seconds": 9}, "beyond"),
                 ({"asset_id": self.image}, "video source"),
                 ({"media_kind": "image"}, "uploaded image"),
                 ({"source_in": float("inf"), "source_out": float("inf")}, "finite")]
        for changes, message in cases:
            with self.subTest(changes=changes):
                original = deepcopy(self.doc["broll"][0])
                self.doc["broll"][0].update(changes)
                with self.assertRaisesRegex(ValueError, message):
                    self.validate()
                self.doc["broll"][0] = original

    def test_overlapping_and_excessive_cover_are_rejected(self):
        self.doc["broll"].append({**self.doc["broll"][0], "start_seconds": 3})
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.validate()
        self.doc["broll"] = [{**self.doc["broll"][0], "start_seconds": n * 2} for n in range(4)]
        with self.assertRaisesRegex(ValueError, "60 percent"):
            self.validate()

    def test_duration_variant_clips_only_overlay_picture(self):
        plan = self.validate()
        shortened = derive_duration_variant(plan, 3)
        self.assertEqual(shortened.clips[0].source_out, 3)
        self.assertEqual(shortened.broll[0].duration_seconds, 1)
        self.assertEqual(shortened.broll[0].source_out, 2)
        self.assertEqual(plan.broll[0].duration_seconds, 2)

    def test_overlay_moves_with_reordered_dialogue_and_disappears_with_removed_clip(self):
        self.doc["clips"] = [{**self.doc["clips"][0], "source_out": 5},
                              {**self.doc["clips"][0], "source_in": 5}]
        plan = self.validate()
        moved = apply_timeline_adjustments(plan, [{"clip_index": 0, "action": "move_down"}])
        self.assertEqual(moved.broll[0].start_seconds, 7)
        deleted = apply_timeline_adjustments(plan, [{"clip_index": 0, "action": "remove"}])
        self.assertEqual(deleted.broll, [])

    def test_overlay_remaps_after_internal_pause_trim(self):
        self.doc["broll"][0].update(start_seconds=7)
        self.assets[0]["transcript_segments"] = [{"words": [
            {"start": 0.1, "end": 2, "text": "setup"}, {"start": 7, "end": 9.9, "text": "payoff"}]}]
        plan = self.validate()
        tightened = apply_timeline_adjustments(plan, [{"clip_index": 0, "max_pause_seconds": 0.6}], self.assets)
        self.assertAlmostEqual(tightened.broll[0].start_seconds, 2.6)
        self.assertEqual(tightened.broll[0].duration_seconds, 2)

    def test_finishing_fills_flat_shots_without_moving_words(self):
        self.doc["clips"][0]["visual_preset"] = "standard"
        repaired, changes = repair_predictable_plan_defaults(self.doc, creative_direction=self.direction,
                                                              complete_creative_defaults=True)
        self.assertEqual(repaired["clips"][0]["visual_preset"], "rhythmic_punch")
        self.assertEqual((repaired["clips"][0]["source_in"], repaired["clips"][0]["source_out"]), (0, 10))
        self.assertIn("added_rhythmic_punch_without_changing_dialogue", changes)
        legacy, _ = repair_predictable_plan_defaults(self.doc, creative_direction=self.direction)
        self.assertEqual(legacy["clips"][0]["visual_preset"], "standard")
        self.doc["clips"][0]["editorial_intent"] = "Hold this reaction and let the line breathe."
        held, _ = repair_predictable_plan_defaults(self.doc, creative_direction=self.direction, complete_creative_defaults=True)
        self.assertEqual(held["clips"][0]["visual_preset"], "standard")

    def test_legacy_plan_serialization_does_not_add_empty_overlay_fields(self):
        self.doc["schema_version"] = "1.3"
        self.doc.pop("broll")
        serialized = TalkingHeadEditPlan.model_validate(self.doc).model_dump(mode="json")
        self.assertNotIn("broll", serialized)

    def test_high_impact_prompt_uses_the_existing_planning_call(self):
        from types import SimpleNamespace

        context = {"job": {"recipe": "talking_head", "edit_style": "high_impact"},
                   "project": {"privacy_mode": "text_only"}, "assets": self.assets}
        prompt = _model_content(context, SimpleNamespace(editor_max_context_characters=120000))[0]["text"]
        self.assertIn("Main speech continues unchanged under broll", prompt)
        self.assertIn("rhythmic_punch", prompt)
        self.assertIn("2–3 seconds", prompt)
        context["job"]["edit_style"] = "clean"
        self.assertNotIn("High impact finishing:", _model_content(context,
            SimpleNamespace(editor_max_context_characters=120000))[0]["text"])

    def test_local_only_high_impact_keeps_the_fixed_recipe_available(self):
        from app.editor_provider import create_edit_plan

        context = {"job": {"recipe": "talking_head", "edit_style": "high_impact", "target_duration_seconds": 30},
                   "project": {"privacy_mode": "local_only"}, "assets": self.assets, "music_library": []}
        settings = Settings(database_url="postgresql://example.invalid/test", upload_hook_secret="x" * 32)
        plan, provenance = create_edit_plan(context, settings)
        validate_edit_plan(plan.model_dump(mode="json"), self.assets, creative_direction=self.direction)
        self.assertEqual(provenance["provider"], "local_fixed_recipe")
        self.assertEqual(provenance["usage"], {})

    def test_high_impact_finishes_long_flat_shots_with_one_planner_call(self):
        from unittest.mock import MagicMock, Mock, patch
        from app import worker

        self.doc["broll"] = []
        self.doc["clips"] = [{**self.doc["clips"][0], "source_out": 6, "visual_preset": "standard"},
                              {**self.doc["clips"][0], "source_in": 6, "visual_preset": "punch_in"}]
        proposed = TalkingHeadEditPlan.model_validate(self.doc)
        context = {"ready_for_editing": True, "job": {"edit_style": "high_impact"},
            "project": {"privacy_mode": "hybrid", "name": "Product ad", "brief": "Keep this story", "ai_copy_allowed": False},
            "assets": self.assets, "music_library": [], "creative_effect_library": []}
        run = {"id": str(uuid4()), "job_id": str(uuid4()), "version": 1, "edit_plan_id": None, "based_on_run_id": None}
        planner = Mock(return_value=(proposed, {"provider": "chatgpt_plan", "model": "test"}))
        renderer = Mock(return_value={"outputs": {"preview": "preview.mp4"}, "manifest_path": "manifest.json"})
        with patch.multiple(worker, claim_pending_edit=Mock(return_value=run), build_editor_context=Mock(return_value=context),
            create_edit_plan=planner, connection=MagicMock(), assert_ai_budget=Mock(), _record_plan_usage=Mock(),
            _persist_generated_plan=Mock(), render_edit_preview=renderer):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_called_once()
        finished = renderer.call_args.args[1]
        self.assertEqual(finished.clips[0].visual_preset, "rhythmic_punch")
        self.assertEqual([(c.source_in, c.source_out) for c in finished.clips], [(0, 6), (6, 10)])

    def test_local_broll_removal_preserves_speech_and_never_calls_a_model(self):
        from unittest.mock import MagicMock, Mock, patch
        from app import worker

        plan = self.validate()
        context = {"ready_for_editing": True, "job": {"edit_style": "high_impact"},
            "project": {"privacy_mode": "hybrid", "name": "Product ad", "brief": "Keep this story", "ai_copy_allowed": False},
            "assets": self.assets, "music_library": [], "creative_effect_library": []}
        run = {"id": str(uuid4()), "job_id": str(uuid4()), "version": 2, "edit_plan_id": None,
               "based_on_run_id": str(uuid4()), "revision_note": None, "broll_enabled": False}
        connection = MagicMock()
        connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
            "version": 1, "document": plan.model_dump(mode="json"), "caption_corrections": []}
        planner = Mock()
        renderer = Mock(return_value={"outputs": {"preview": "preview.mp4"}, "manifest_path": "manifest.json"})
        with patch.multiple(worker, claim_pending_edit=Mock(return_value=run),
            build_editor_context=Mock(return_value=context), create_edit_plan=planner, connection=connection,
            _record_plan_usage=Mock(), _persist_generated_plan=Mock(), render_edit_preview=renderer):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_not_called()
        rendered = renderer.call_args.args[1]
        self.assertEqual(rendered.broll, [])
        self.assertEqual(rendered.clips, plan.clips)
        self.assertEqual(len(plan.broll), 1)

    def test_new_planning_removes_unsynchronised_speaking_cover_with_one_model_call(self):
        from unittest.mock import MagicMock, Mock, patch
        from app import worker

        self.assets[1]["transcript_segments"] = [{"start": 1, "end": 3, "text": "A different spoken take."}]
        proposed = TalkingHeadEditPlan.model_validate(self.doc)
        context = {"ready_for_editing": True, "job": {"edit_style": "high_impact"},
            "project": {"privacy_mode": "hybrid", "name": "Product ad", "brief": "Keep this story", "ai_copy_allowed": False},
            "assets": self.assets, "music_library": [], "creative_effect_library": []}
        run = {"id": str(uuid4()), "job_id": str(uuid4()), "version": 1, "edit_plan_id": None, "based_on_run_id": None}
        planner = Mock(return_value=(proposed, {"provider": "chatgpt_plan", "model": "test"}))
        renderer = Mock(return_value={"outputs": {"preview": "preview.mp4"}, "manifest_path": "manifest.json"})
        with patch.multiple(worker, claim_pending_edit=Mock(return_value=run), build_editor_context=Mock(return_value=context),
            create_edit_plan=planner, connection=MagicMock(), assert_ai_budget=Mock(), _record_plan_usage=Mock(),
            _persist_generated_plan=Mock(), render_edit_preview=renderer):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_called_once()
        rendered_context, rendered_plan = renderer.call_args.args[:2]
        self.assertEqual(rendered_plan.clips, proposed.clips)
        self.assertEqual(rendered_plan.broll, [])
        self.assertEqual(len(proposed.broll), 1)
        self.assertEqual(rendered_context["broll_selection_review"][0]["asset_id"], self.cover)

    def test_overlay_filter_keeps_audio_and_places_captions_after_picture(self):
        plan = self.validate()
        graph = append_broll_filters("[base]subtitles=filename='captions.ass'[vout];[voice]anull[aout]",
            [{"cue": plan.broll[0], "input_index": 1}], width=160, height=284, fps=30)
        self.assertIn("[voice]anull[aout]", graph)
        self.assertGreater(graph.index("subtitles="), graph.index("overlay="))
        self.assertIn("gte(t,2.000)*lt(t,4.000)", graph)
        self.assertIn("eof_action=pass:repeatlast=0", graph)
        self.assertIn("mod(on,150),75", rhythmic_zoom(30))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_real_overlay_switches_picture_but_preserves_decoded_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, cover = root / "base.mp4", root / "cover.mp4"
            for path, colour, frequency in [(base, "red", 440), (cover, "blue", 1900)]:
                run_command(["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi", "-i", f"color={colour}:s=160x284:r=30:d=3",
                    "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)], timeout=15)
            image = root / "image.png"
            run_command(["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi", "-i", "color=green:s=160x284:d=0.04",
                         "-frames:v", "1", "-threads", "1", str(image)], timeout=10)
            self.doc["clips"][0].update(source_out=3, visual_preset="rhythmic_punch")
            self.doc["broll"][0].update(source_in=0, source_out=1, start_seconds=1, duration_seconds=1)
            self.doc["broll"].append({"asset_id": self.image, "media_kind": "image", "source_in": 0,
                "source_out": 0, "start_seconds": 2, "duration_seconds": 0.7, "editorial_intent": "Show the product still."})
            plan = self.validate()
            captions = root / "captions.ass"
            captions.write_text(render_ass([]))
            baseline, layered = root / "baseline.mp4", root / "layered.mp4"
            cue = CreativeEffectCue(asset_id=uuid4(), start_seconds=0.5, duration_seconds=0.25)
            effects = [{"cue": cue, "path": cover, "kind": "sound_effect", "input_index": 1}]
            self.assets[0]["_storage_key"] = base.name
            self.assets[1]["_storage_key"] = cover.name
            self.assets[2]["_storage_key"] = image.name
            settings = Settings(database_url="postgresql://example.invalid/test", upload_hook_secret="x" * 32, media_root=root)
            context = {"assets": self.assets, "job": {"edit_style": "high_impact"}, "music_library": []}
            broll = selected_broll(context, plan, settings, 2)
            _render_video([(base, 0, 3)], plan, captions, baseline, 30, width=160, height=284, effect_sources=effects)
            _render_video([(base, 0, 3)], plan, captions, layered, 30, width=160, height=284,
                effect_sources=effects, broll_sources=broll)
            def audio(path):
                import subprocess
                return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-"])
            self.assertEqual(audio(baseline), audio(layered), "B-roll audio must not enter the speech mix")
            import subprocess
            for seek, dominant in [(0.5, 0), (1.5, 2), (2.3, 1), (2.9, 0)]:
                pixel = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(seek), "-i", str(layered),
                    "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                self.assertEqual(max(range(3), key=lambda channel: pixel[channel]), dominant)

            from app.montage_renderer import _render
            from app.edit_plan import MontageEditPlan
            montage = MontageEditPlan(schema_version="1.4", recipe="montage", audio_preset="montage_mix_v1",
                end_card="none", editorial_summary="Keep continuous speech under the cover shots.", broll=plan.broll,
                clips=[{"asset_id": self.voice, "media_kind": "video", "source_in": n * 1.5,
                        "source_out": (n + 1) * 1.5, "duration": 1.5, "crop": "center_fill", "include_source_audio": True}
                       for n in range(2)])
            montage_baseline, montage_layered = root / "montage-base.mp4", root / "montage-layer.mp4"
            _render(context, montage.model_copy(update={"broll": []}), montage_baseline, width=160, height=284,
                    final=False, settings=settings)
            _render(context, montage, montage_layered, width=160, height=284, final=False, settings=settings)
            self.assertEqual(audio(montage_baseline), audio(montage_layered))


if __name__ == "__main__":
    unittest.main()
