"""Re-rendering a saved edit must not re-plan its dialogue or cutaways."""

from copy import deepcopy
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from app import worker
from app.duration_policy import duration_settings


class RenderRebuildTests(unittest.TestCase):
    def test_saved_speech_and_montage_plans_render_unchanged_without_model_usage(self):
        for recipe in ("talking_head", "montage"):
            with self.subTest(recipe=recipe):
                voice, cutaway = str(uuid4()), str(uuid4())
                document = {
                    "schema_version": "1.4",
                    "recipe": recipe,
                    "clips": [
                        {
                            "asset_id": voice,
                            "source_in": 1,
                            "source_out": 4,
                            "crop": "center_fill",
                            "visual_preset": "punch_in",
                        }
                    ],
                    "caption_style": "clean_blue_v1",
                    "end_card": "none",
                    "audio_preset": "spoken_voice_v1"
                    if recipe == "talking_head"
                    else "montage_mix_v1",
                    "editorial_summary": "Keep the chosen story and supporting picture.",
                    "broll": [
                        {
                            "asset_id": cutaway,
                            "media_kind": "video",
                            "source_in": 0,
                            "source_out": 1,
                            "start_seconds": 1,
                            "duration_seconds": 1,
                            "editorial_intent": "The selected cutaway.",
                        }
                    ],
                }
                if recipe == "montage":
                    document["clips"][0].update(
                        media_kind="video", duration=3, include_source_audio=True
                    )
                    document.pop("caption_style")
                    document["clips"].append(
                        {**document["clips"][0], "source_in": 4, "source_out": 7}
                    )
                original = deepcopy(document)
                context = {
                    "ready_for_editing": True,
                    "project": {
                        "name": "Saved story",
                        "brief": "Keep this edit.",
                        "ai_copy_allowed": False,
                    },
                    "job": {
                        "recipe": recipe,
                        "edit_style": "high_impact",
                        "music_mode": "none",
                        "duration_mode": "strict",
                        "target_duration_seconds": 60,
                    },
                    "assets": [
                        dict(
                            asset_id=identity,
                            has_video=True,
                            has_audio=True,
                            duration_seconds=10,
                            mime_type="video/mp4",
                            library_role="talking",
                        )
                        for identity in (voice, cutaway)
                    ],
                    "music_library": [],
                    "creative_effect_library": [],
                }
                # Use the same persisted settings structure as the rebuild route.
                snapshot = duration_settings(
                    {
                        "duration_mode": "follow_story",
                        "target_duration_seconds": 30,
                        "max_duration_seconds": 90,
                    }
                )
                run = dict(
                    id=str(uuid4()),
                    job_id=str(uuid4()),
                    version=2,
                    edit_plan_id=str(uuid4()),
                    based_on_run_id=str(uuid4()),
                    duration_policy=snapshot,
                )
                database = MagicMock()
                database.execute.return_value.fetchone.side_effect = [
                    {"speech_precision_snapshot": {}},
                    {
                        "document": document,
                        "provider": "chatgpt_plan",
                        "model": "saved-model",
                    },
                    {"document": document, "caption_corrections": []},
                ]
                renderer = Mock(
                    return_value={
                        "outputs": {"preview": "preview.mp4"},
                        "manifest_path": "manifest.json",
                    }
                )
                planner, usage, guard, persistence = Mock(), Mock(), Mock(), Mock()
                with patch.multiple(
                    worker,
                    claim_pending_edit=Mock(return_value=run),
                    build_editor_context=Mock(return_value=context),
                    connection=MagicMock(return_value=database),
                    create_edit_plan=planner,
                    _record_plan_usage=usage,
                    _guard_generated_broll=guard,
                    _persist_generated_plan=persistence,
                    render_edit_preview=renderer,
                    render_montage_preview=renderer,
                ):
                    database.__enter__.return_value = database
                    self.assertTrue(worker.process_one_edit(worker.WorkerState()))
                renderer.assert_called_once()
                result = renderer.call_args.args[1].model_dump(mode="json")
                self.assertEqual(result["clips"][0]["source_in"], 1)
                self.assertEqual(result["clips"][0]["source_out"], 4)
                self.assertEqual(result["clips"][0]["visual_preset"], "punch_in")
                self.assertEqual(result["broll"][0]["asset_id"], cutaway)
                self.assertEqual(result["broll"][0]["start_seconds"], 1)
                self.assertEqual(context["job"]["duration_mode"], "follow_story")
                self.assertEqual(context["job"]["max_duration_seconds"], 90)
                self.assertEqual(document, original)
                for operation in (planner, usage, guard, persistence):
                    operation.assert_not_called()
                self.assertFalse(
                    any(
                        "status = 'failed'" in call.args[0]
                        for call in database.execute.call_args_list
                    )
                )
