import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.config import Settings
from app.edit_plan import (
    MontageEditPlan,
    deterministic_montage_plan,
    repair_predictable_plan_defaults,
    validate_edit_plan,
)
from app.editor_provider import _model_content, _parse_sse_response
from app.montage_renderer import (
    _ffmpeg_failure_detail,
    _filter_graph,
    _render_source,
    _timing_error,
    montage_caption_events,
)


class MontagePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.video_id = uuid4()
        self.image_id = uuid4()
        self.assets = [
            {
                "asset_id": str(self.video_id),
                "mime_type": "video/mp4",
                "duration_seconds": 20.0,
                "has_video": True,
                "has_audio": True,
            },
            {
                "asset_id": str(self.image_id),
                "mime_type": "image/jpeg",
                "duration_seconds": 0.0,
                "has_video": False,
                "has_audio": False,
            },
        ]
        self.document = {
            "schema_version": "1.0",
            "recipe": "montage",
            "clips": [
                {
                    "asset_id": str(self.video_id),
                    "media_kind": "video",
                    "source_in": 0,
                    "source_out": 7.5,
                    "duration": 7.5,
                    "crop": "center_fill",
                    "transition": "cut",
                    "visual_preset": "punch_in",
                    "include_source_audio": True,
                },
                {
                    "asset_id": str(self.image_id),
                    "media_kind": "image",
                    "source_in": 0,
                    "source_out": 0,
                    "duration": 7.5,
                    "crop": "center_fill",
                    "transition": "dip_to_black",
                    "visual_preset": "slow_push_in",
                    "include_source_audio": False,
                },
            ],
            "audio_preset": "montage_mix_v1",
            "end_card": "none",
            "editorial_summary": "A short source-led montage.",
            "post_copy": "",
            "music_track_id": None,
            "music_mix": "none",
        }

    def test_accepts_video_and_image_montage(self) -> None:
        plan = validate_edit_plan(
            self.document,
            self.assets,
            creative_direction={"target_duration_seconds": 15, "music_mode": "none"},
        )

        self.assertIsInstance(plan, MontageEditPlan)
        self.assertEqual(sum(clip.duration for clip in plan.clips), 15)
        self.assertEqual(plan.clips[0].source_audio_gain_db, 0)

    def test_accepts_bounded_gain_for_an_audible_video_clip(self) -> None:
        self.document["clips"][0]["source_audio_gain_db"] = 10

        plan = validate_edit_plan(self.document, self.assets)

        self.assertEqual(plan.clips[0].source_audio_gain_db, 10)

    def test_rejects_gain_for_a_muted_clip(self) -> None:
        self.document["clips"][0]["include_source_audio"] = False
        self.document["clips"][0]["source_audio_gain_db"] = 6

        with self.assertRaisesRegex(ValueError, "muted montage clips"):
            validate_edit_plan(self.document, self.assets)

    def test_predictable_music_omission_is_repaired_without_another_model_call(self) -> None:
        track_id = uuid4()

        repaired, repairs = repair_predictable_plan_defaults(
            self.document,
            creative_direction={"music_mode": "subtle"},
            music_tracks=[{"track_id": str(track_id)}],
        )

        self.assertEqual(repaired["music_track_id"], str(track_id))
        self.assertEqual(repaired["music_mix"], "subtle")
        self.assertEqual(repairs, ["selected_first_approved_music_track"])

    def test_music_repair_preserves_the_previous_approved_track(self) -> None:
        first_track_id = uuid4()
        previous_track_id = uuid4()

        repaired, repairs = repair_predictable_plan_defaults(
            self.document,
            creative_direction={"music_mode": "subtle"},
            music_tracks=[
                {"track_id": str(first_track_id)},
                {"track_id": str(previous_track_id)},
            ],
            previous_plan={"music_track_id": str(previous_track_id)},
        )

        self.assertEqual(repaired["music_track_id"], str(previous_track_id))
        self.assertEqual(repairs, ["preserved_previous_approved_music_track"])

    def test_rejects_image_source_timecodes(self) -> None:
        self.document["clips"][1]["source_out"] = 1

        with self.assertRaisesRegex(ValueError, "zero source timecodes"):
            validate_edit_plan(self.document, self.assets)

    def test_rejects_video_duration_mismatch(self) -> None:
        self.document["clips"][0]["duration"] = 6

        with self.assertRaisesRegex(ValueError, "must match"):
            validate_edit_plan(self.document, self.assets)

    def test_rejects_unknown_generation_instruction(self) -> None:
        self.document["clips"][0]["generate_transition"] = True

        with self.assertRaises(ValidationError):
            validate_edit_plan(self.document, self.assets)

    def test_local_montage_builds_requested_duration(self) -> None:
        plan = deterministic_montage_plan(
            self.assets,
            target_duration_seconds=15,
            edit_style="energetic",
            music_mode="none",
            music_tracks=[],
        )

        self.assertAlmostEqual(sum(clip.duration for clip in plan.clips), 15, places=2)
        self.assertGreaterEqual(len(plan.clips), 2)

    def test_validation_correction_is_sent_as_a_bounded_repair(self) -> None:
        settings = Settings(
            database_url="postgresql://example.invalid/test",
            upload_hook_secret="x" * 32,
        )
        context = {
            "job": {"recipe": "montage"},
            "project": {"privacy_mode": "text_only", "ai_copy_allowed": False},
            "assets": self.assets,
            "music_library": [],
            "validation_correction": {
                "error": f"asset {self.video_id} contains overlapping source ranges",
                "rejected_plan": self.document,
            },
        }

        content = _model_content(context, settings)
        prompt = str(content[0]["text"])

        self.assertIn("deterministic validator", prompt)
        self.assertIn("overlapping source ranges", prompt)
        self.assertIn("complete replacement plan", prompt)


class MontageFilterTests(unittest.TestCase):
    def test_maps_only_audible_video_speech_to_montage_timeline(self) -> None:
        audible_id = uuid4()
        muted_id = uuid4()
        image_id = uuid4()
        plan = MontageEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "montage",
                "clips": [
                    {
                        "asset_id": str(image_id), "media_kind": "image",
                        "source_in": 0, "source_out": 0, "duration": 2,
                        "crop": "center_fill", "transition": "cut",
                        "visual_preset": "standard", "include_source_audio": False,
                    },
                    {
                        "asset_id": str(audible_id), "media_kind": "video",
                        "source_in": 10, "source_out": 14, "duration": 4,
                        "crop": "center_fill", "transition": "cut",
                        "visual_preset": "standard", "include_source_audio": True,
                    },
                    {
                        "asset_id": str(muted_id), "media_kind": "video",
                        "source_in": 0, "source_out": 2, "duration": 2,
                        "crop": "center_fill", "transition": "cut",
                        "visual_preset": "standard", "include_source_audio": False,
                    },
                ],
                "audio_preset": "montage_mix_v1",
                "end_card": "none",
                "editorial_summary": "Caption mapping test.",
                "post_copy": "",
                "music_track_id": None,
                "music_mix": "none",
            }
        )
        assets = [
            {"asset_id": str(image_id), "transcript_segments": []},
            {
                "asset_id": str(audible_id),
                "transcript_segments": [
                    {"start": 9.5, "end": 11, "text": "Hallo world"},
                    {"start": 13, "end": 14.5, "text": "Second line"},
                ],
            },
            {
                "asset_id": str(muted_id),
                "transcript_segments": [{"start": 0, "end": 1, "text": "Do not show"}],
            },
        ]

        events = montage_caption_events(
            plan,
            assets,
            [{"original_text": "Hallo", "replacement_text": "Hello"}],
        )

        self.assertEqual(
            events,
            [
                {"start": 2.0, "end": 3.0, "text": "Hello world"},
                {"start": 5.0, "end": 6.0, "text": "Second line"},
            ],
        )

    def test_image_render_uses_the_normalized_analysis_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            media_root = Path(directory)
            original = media_root / "originals" / "asset" / "source"
            preview = media_root / "previews" / "asset" / "preview.jpg"
            proxy = media_root / "proxies" / "asset" / "proxy.mp4"
            original.parent.mkdir(parents=True)
            preview.parent.mkdir(parents=True)
            proxy.parent.mkdir(parents=True)
            original.write_bytes(b"original")
            preview.write_bytes(b"normalized")
            proxy.write_bytes(b"normalized-video")
            settings = Settings(
                database_url="postgresql://example.invalid/test",
                upload_hook_secret="x" * 32,
                media_root=media_root,
            )
            asset = {
                "_storage_key": "originals/asset/source",
                "_preview_key": "previews/asset/preview.jpg",
                "_proxy_key": "proxies/asset/proxy.mp4",
            }

            self.assertEqual(
                _render_source(settings, asset, media_kind="image"),
                preview,
            )
            self.assertEqual(
                _render_source(settings, asset, media_kind="video"),
                proxy,
            )

    def test_ffmpeg_failure_detail_keeps_the_actionable_lines(self) -> None:
        detail = _ffmpeg_failure_detail(
            "noise\n[Parsed_concat_1] Input link parameters do not match\n"
            "Error while filtering: Invalid argument\nConversion failed!\n"
        )

        self.assertIn("Input link parameters do not match", detail)
        self.assertNotIn("Conversion failed", detail)

    def test_filter_graph_normalizes_video_and_audio_for_concat(self) -> None:
        video_id = uuid4()
        image_id = uuid4()
        plan = MontageEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "montage",
                "clips": [
                    {
                        "asset_id": str(video_id),
                        "media_kind": "video",
                        "source_in": 0,
                        "source_out": 2,
                        "duration": 2,
                        "crop": "center_fill",
                        "transition": "cut",
                        "visual_preset": "standard",
                        "include_source_audio": True,
                        "source_audio_gain_db": 10,
                    },
                    {
                        "asset_id": str(image_id),
                        "media_kind": "image",
                        "source_in": 0,
                        "source_out": 0,
                        "duration": 2,
                        "crop": "center_fill",
                        "transition": "cut",
                        "visual_preset": "slow_push_in",
                        "include_source_audio": False,
                    },
                ],
                "audio_preset": "montage_mix_v1",
                "end_card": "none",
                "editorial_summary": "Filter test.",
                "post_copy": "",
                "music_track_id": None,
                "music_mix": "none",
            }
        )

        graph = _filter_graph(
            plan,
            {
                str(video_id): {"has_audio": True},
                str(image_id): {"has_audio": False},
            },
            width=540,
            height=960,
            fps=30,
            music_input_index=None,
        )

        self.assertIn("format=yuv420p", graph)
        self.assertIn("channel_layouts=stereo", graph)
        self.assertIn("concat=n=2:v=1:a=1", graph)
        self.assertIn("zoompan", graph)
        self.assertIn("d=60", graph)
        self.assertIn("apad=pad_dur=2.000", graph)
        self.assertIn("trim=duration=4.000", graph)
        self.assertIn("afade=t=in:st=0:d=0.080", graph)
        self.assertIn("volume=2.000dB", graph)

        graph_with_music = _filter_graph(
            plan,
            {
                str(video_id): {"has_audio": True},
                str(image_id): {"has_audio": False},
            },
            width=540,
            height=960,
            fps=30,
            music_input_index=2,
        )
        self.assertIn("sidechaincompress", graph_with_music)
        self.assertIn("asplit=2[source][key]", graph_with_music)
        self.assertGreaterEqual(graph_with_music.count("channel_layouts=stereo"), 4)
        self.assertIn("[2:a:0]aresample=48000,atrim=0:4.000,aformat=", graph_with_music)

    def test_static_image_uses_one_decoded_frame(self) -> None:
        image_id = uuid4()
        plan = MontageEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "montage",
                "clips": [
                    {
                        "asset_id": str(image_id),
                        "media_kind": "image",
                        "source_in": 0,
                        "source_out": 0,
                        "duration": 2.5,
                        "crop": "center_fill",
                        "transition": "cut",
                        "visual_preset": "standard",
                        "include_source_audio": False,
                    },
                    {
                        "asset_id": str(image_id),
                        "media_kind": "image",
                        "source_in": 0,
                        "source_out": 0,
                        "duration": 2.5,
                        "crop": "center_fill",
                        "transition": "cut",
                        "visual_preset": "slow_pull_out",
                        "include_source_audio": False,
                    },
                ],
                "audio_preset": "montage_mix_v1",
                "end_card": "none",
                "editorial_summary": "Still-frame efficiency test.",
                "post_copy": "",
                "music_track_id": None,
                "music_mix": "none",
            }
        )

        graph = _filter_graph(
            plan,
            {str(image_id): {"has_audio": False}},
            width=540,
            height=960,
            fps=30,
            music_input_index=None,
        )

        self.assertIn("tpad=stop_mode=clone:stop_duration=2.500", graph)
        self.assertIn("d=75", graph)

    def test_timing_qa_rejects_truncated_or_desynchronized_tracks(self) -> None:
        self.assertIsNone(
            _timing_error(
                {
                    "streams": [
                        {"type": "video", "duration_seconds": 30.0},
                        {"type": "audio", "duration_seconds": 30.02},
                    ]
                },
                30.0,
            )
        )
        self.assertIn(
            "video is 26.567s",
            _timing_error(
                {
                    "streams": [
                        {"type": "video", "duration_seconds": 26.567},
                        {"type": "audio", "duration_seconds": 25.375},
                    ]
                },
                30.0,
            )
            or "",
        )


class ProviderUsageTests(unittest.TestCase):
    def test_collects_streamed_plan_and_token_usage(self) -> None:
        plan = json.dumps({"recipe": "montage"})
        response = [
            f'data: {json.dumps({"type": "response.output_text.delta", "delta": plan})}\n'.encode(),
            (
                "data: "
                + json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_test",
                            "model": "gpt-test",
                            "usage": {
                                "input_tokens": 100,
                                "input_tokens_details": {"cached_tokens": 40},
                                "output_tokens": 25,
                                "output_tokens_details": {"reasoning_tokens": 10},
                                "total_tokens": 125,
                            },
                        },
                    }
                )
                + "\n"
            ).encode(),
        ]

        output, usage = _parse_sse_response(response)

        self.assertEqual(output, plan)
        self.assertEqual(usage["response_id"], "resp_test")
        self.assertEqual(usage["cached_input_tokens"], 40)
        self.assertEqual(usage["reasoning_tokens"], 10)
        self.assertEqual(usage["total_tokens"], 125)


if __name__ == "__main__":
    unittest.main()
