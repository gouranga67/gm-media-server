import json
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from app import edit_renderer, montage_renderer
from app.config import Settings
from app.edit_plan import MontageEditPlan, TalkingHeadEditPlan


class QualityRenderIntegrationTests(unittest.TestCase):
    def test_report_is_persisted_for_both_recipes_and_packaged_in_final_exports(self):
        for montage in (False, True):
            with self.subTest(montage=montage), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                settings = Settings(database_url="postgresql://example.invalid/test", upload_hook_secret="x" * 32,
                                    media_root=root)
                asset_id = str(uuid4())
                context = {"job": {"id": str(uuid4()), "project_id": str(uuid4()), "output_aspect": "vertical"},
                           "project": {}, "assets": [{"asset_id": asset_id, "transcript_segments": []}],
                           "music_library": [], "creative_effect_library": []}
                clip = {"asset_id": asset_id, "source_in": 0, "source_out": 2, "crop": "center_fill"}
                if montage:
                    clip.update(media_kind="video", duration=2, include_source_audio=True)
                    plan = MontageEditPlan(schema_version="1.3", recipe="montage", clips=[clip, dict(clip)],
                        audio_preset="montage_mix_v1", end_card="none", editorial_summary="The original montage.")
                    renderer = montage_renderer
                else:
                    plan = TalkingHeadEditPlan(schema_version="1.3", recipe="talking_head", clips=[clip],
                        caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none",
                        editorial_summary="The original story.")
                    renderer = edit_renderer
                review = {"version": "1.0", "status": "passed", "additional_model_tokens": 0,
                          "checks": [], "findings": [], "finding_count": 0, "automatic_changes": []}
                qa = Mock(return_value=review)
                probe = {"format": {"duration_seconds": 4 if montage else 2}, "streams": [
                    {"type": "video", "width": 1080, "height": 1920}, {"type": "audio"}]}

                def write_output(path):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"encoded test fixture")
                    return "test_encoder"

                if montage:
                    stack.enter_context(patch.object(renderer, "_render", side_effect=lambda c, p, output, **kw: write_output(output)))
                else:
                    stack.enter_context(patch.object(renderer, "resolve_internal_asset_render_source", return_value=root / "source.mp4"))
                    stack.enter_context(patch.object(renderer, "_render_video", side_effect=lambda sources, p, caps, output, *args, **kw: write_output(output)))
                stack.enter_context(patch.object(renderer, "generate_file", side_effect=lambda command, output, *args, **kw: write_output(output)))
                stack.enter_context(patch.object(renderer, "ensure_capacity", return_value={"free_bytes": 100000000000}))
                stack.enter_context(patch.object(renderer, "probe_media", return_value=probe))
                stack.enter_context(patch.object(renderer, "_ffmpeg_version", return_value="test"))
                stack.enter_context(patch.object(renderer, "review_rendered_video", qa))

                preview_fn = renderer.render_montage_preview if montage else renderer.render_edit_preview
                final_fn = renderer.render_montage_delivery if montage else renderer.render_final_delivery
                preview = preview_fn(context, plan, 1, "validated_edl", "test", settings=settings)
                final = final_fn(context, plan, 1, "validated_edl", "test", [], "2026-10-26T00:00:00Z", settings=settings)
                self.assertEqual(qa.call_count, 2)
                self.assertNotIn("probe", qa.call_args_list[0].kwargs)
                self.assertEqual(qa.call_args_list[1].kwargs["probe"], probe)
                for manifest in (preview, final):
                    self.assertEqual(manifest["quality_review"], review)
                    stored = json.loads((root / manifest["manifest_path"]).read_text())
                    self.assertEqual(stored["quality_review"], review)
                with zipfile.ZipFile(root / final["outputs"]["package"]) as package:
                    packaged = json.loads(package.read("gm-studio-manifest.json"))
                    self.assertEqual(packaged["quality_review"], review)


if __name__ == "__main__":
    unittest.main()
