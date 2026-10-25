import tempfile
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan
from app.edit_renderer import (
    _clip_video_filter,
    _create_delivery_package,
    _ffmpeg_failure_detail,
    _ffmpeg_filter,
    caption_events,
    render_ass,
)


class CaptionMappingTests(unittest.TestCase):
    def test_ffmpeg_failure_detail_keeps_actionable_tail(self) -> None:
        detail = _ffmpeg_failure_detail(
            "configuration header\n"
            "[Parsed_sidechaincompress_0] Invalid argument\n"
            "Input link in0 parameters (size 1920x1080) do not match\n"
            "Error while filtering: Invalid argument\n"
            "Conversion failed!\n"
        )

        self.assertIn("sidechaincompress", detail)
        self.assertIn("Input link", detail)
        self.assertNotIn("configuration header", detail)
        self.assertNotIn("Conversion failed", detail)

    def test_maps_source_captions_to_concatenated_timeline(self) -> None:
        first = uuid4()
        second = uuid4()
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "talking_head",
                "clips": [
                    {
                        "asset_id": str(first),
                        "source_in": 10,
                        "source_out": 15,
                        "crop": "center_fill",
                        "transition": "cut",
                    },
                    {
                        "asset_id": str(second),
                        "source_in": 2,
                        "source_out": 5,
                        "crop": "center_fill",
                        "transition": "cut",
                    },
                ],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Two source excerpts.",
            }
        )
        assets = [
            {
                "asset_id": str(first),
                "transcript_segments": [{"start": 11, "end": 12, "text": "First"}],
            },
            {
                "asset_id": str(second),
                "transcript_segments": [{"start": 3, "end": 4, "text": "Second"}],
            },
        ]

        events = caption_events(plan, assets)

        self.assertEqual(events[0], {"start": 1.0, "end": 2.0, "text": "First"})
        self.assertEqual(events[1], {"start": 6.0, "end": 7.0, "text": "Second"})
        ass = render_ass(events)
        self.assertIn("0:00:01.00,0:00:02.00", ass)
        self.assertIn("0:00:06.00,0:00:07.00", ass)

    def test_applies_only_explicit_caption_replacements(self) -> None:
        asset_id = uuid4()
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.0",
                "recipe": "talking_head",
                "clips": [
                    {
                        "asset_id": str(asset_id),
                        "source_in": 0,
                        "source_out": 3,
                        "crop": "center_fill",
                        "transition": "cut",
                    }
                ],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Caption correction test.",
            }
        )
        events = caption_events(
            plan,
            [
                {
                    "asset_id": str(asset_id),
                    "transcript_segments": [
                        {"start": 0, "end": 2, "text": "Welcome to Sidney today"}
                    ],
                }
            ],
            [{"original_text": "Sidney", "replacement_text": "Sydney"}],
        )

        self.assertEqual(events[0]["text"], "Welcome to Sydney today")

    def test_long_whisper_segment_becomes_progressive_caption_cards(self) -> None:
        asset_id = uuid4()
        words = [
            {"start": index * 0.4, "end": index * 0.4 + 0.35, "text": word}
            for index, word in enumerate(
                "Do you love castor oil because so do we and here is why".split()
            )
        ]
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.2",
                "recipe": "talking_head",
                "clips": [{
                    "asset_id": str(asset_id), "source_in": 0, "source_out": 5,
                    "crop": "center_fill", "transition": "cut",
                }],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Progressive captions.",
            }
        )

        events = caption_events(
            plan,
            [{"asset_id": str(asset_id), "transcript_segments": [{
                "start": 0, "end": 5, "text": " ".join(word["text"] for word in words), "words": words,
            }]}],
        )

        self.assertGreater(len(events), 1)
        self.assertLessEqual(max(len(event["text"].split()) for event in events), 7)
        self.assertGreater(events[1]["start"], events[0]["start"])
        self.assertNotEqual(events[0]["text"], events[-1]["text"])

    def test_scales_ass_layout_for_final_delivery(self) -> None:
        ass = render_ass(
            [{"start": 0, "end": 1, "text": "Final"}],
            width=1080,
            height=1920,
        )

        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("GMBlue,Arial,68", ass)

    def test_scales_ass_layout_for_landscape_preview(self) -> None:
        ass = render_ass(
            [{"start": 0, "end": 1, "text": "Landscape"}],
            width=960,
            height=540,
        )

        self.assertIn("PlayResX: 960", ass)
        self.assertIn("PlayResY: 540", ass)
        self.assertIn("GMBlue,Arial,19", ass)

    def test_brand_kit_changes_caption_type_and_accent(self) -> None:
        ass = render_ass(
            [{"start": 0, "end": 1, "text": "Brand"}],
            brand_kit={"caption_style": "bold", "font_family": "mono", "accent_color": "#FF0000"},
        )

        self.assertIn("GMBlue,DejaVu Sans Mono,38", ass)
        self.assertIn("&H000000FF", ass)

    def test_builds_bounded_push_in_filter(self) -> None:
        result = _clip_video_filter(
            index=0,
            duration=4.0,
            visual_preset="slow_push_in",
            fade_in=False,
            fade_out=False,
            width=540,
            height=960,
            frames_per_second=30,
        )

        self.assertIn("zoompan", result)
        self.assertIn("min(1+0.12*on/119,1.12)", result)
        self.assertIn("format=yuv420p", result)
        self.assertIn("trim=duration=4.000", result)

    def test_hdr_clip_is_tone_mapped_before_scaling(self) -> None:
        result = _clip_video_filter(
            index=0,
            duration=4.0,
            visual_preset="standard",
            fade_in=False,
            fade_out=False,
            width=540,
            height=960,
            frames_per_second=30,
            tone_map_to_sdr=True,
        )

        self.assertIn("tonemap=mobius", result)
        self.assertLess(result.index("tonemap=mobius"), result.index("scale=540:960"))

    def test_music_filter_ducks_approved_track_under_voice(self) -> None:
        asset_id = uuid4()
        plan = TalkingHeadEditPlan.model_validate(
            {
                "schema_version": "1.1",
                "recipe": "talking_head",
                "clips": [
                    {
                        "asset_id": str(asset_id),
                        "source_in": 0,
                        "source_out": 4,
                        "crop": "center_fill",
                        "transition": "cut",
                        "visual_preset": "punch_in",
                    }
                ],
                "caption_style": "clean_blue_v1",
                "audio_preset": "spoken_voice_v1",
                "end_card": "none",
                "editorial_summary": "Music test.",
                "post_copy": "",
                "music_track_id": str(uuid4()),
                "music_mix": "subtle",
            }
        )

        result = _ffmpeg_filter(
            plan,
            Path("/tmp/captions.ass"),
            width=540,
            height=960,
            frames_per_second=30,
            music_input_index=1,
        )

        self.assertIn("sidechaincompress", result)
        self.assertIn("volume=-9dB", result)
        self.assertIn("loudnorm=I=-18", result)
        self.assertIn(
            "loudnorm=I=-18:LRA=11:TP=-1.5,aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
            result,
        )
        self.assertIn("threshold=0.080:ratio=4", result)
        self.assertGreaterEqual(result.count("channel_layouts=stereo"), 3)
        self.assertIn("apad=pad_dur=4.000", result)

    def test_delivery_package_contains_only_named_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "video_path": root / "final.mp4",
                "captions_path": root / "captions.vtt",
                "cover_path": root / "cover.jpg",
                "manifest_path": root / "manifest.json",
            }
            for name, path in files.items():
                path.write_bytes(name.encode("utf-8"))
            destination = root / "delivery.zip"

            _create_delivery_package(destination, **files)

            self.assertEqual(destination.stat().st_mode & 0o777, 0o440)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "gm-studio-final.mp4",
                        "gm-studio-captions.vtt",
                        "gm-studio-cover.jpg",
                        "gm-studio-manifest.json",
                    },
                )

    def test_delivery_package_includes_opted_in_post_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "video_path": root / "final.mp4",
                "captions_path": root / "captions.vtt",
                "cover_path": root / "cover.jpg",
                "manifest_path": root / "manifest.json",
                "post_copy_path": root / "post-copy.txt",
            }
            for name, path in files.items():
                path.write_bytes(name.encode("utf-8"))
            destination = root / "delivery.zip"

            _create_delivery_package(destination, **files)

            with zipfile.ZipFile(destination) as archive:
                self.assertIn("gm-studio-post-copy.txt", archive.namelist())


if __name__ == "__main__":
    unittest.main()
