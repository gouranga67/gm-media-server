import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from app.edit_plan import TalkingHeadEditPlan, document_sha256
from app.finishing_tools import (
    FinishingTools,
    finish_caption_events,
    validate_finishing,
)
from app.edit_renderer import _render_video, render_ass
from app.media_analysis import run_command


class FinishingToolTests(unittest.TestCase):
    def plan(self, tools=None):
        return TalkingHeadEditPlan(
            schema_version="1.5" if tools else "1.4",
            recipe="talking_head",
            caption_style="clean_blue_v1",
            audio_preset="spoken_voice_v1",
            end_card="none",
            editorial_summary="A complete source story.",
            clips=[
                dict(asset_id=uuid4(), source_in=0, source_out=3, crop="center_fill")
            ],
            finishing=tools,
        )

    def test_legacy_plan_serialization_does_not_add_a_finishing_default(self):
        plan = self.plan()
        self.assertNotIn("finishing", plan.model_dump(mode="json"))
        self.assertEqual(
            document_sha256(plan.model_dump(mode="json")),
            document_sha256(
                TalkingHeadEditPlan.model_validate(
                    plan.model_dump(mode="json")
                ).model_dump(mode="json")
            ),
        )

    def test_bad_ranges_and_arbitrary_filter_expressions_are_rejected(self):
        with self.assertRaises(ValidationError):
            FinishingTools.model_validate(
                {
                    "motions": [
                        {
                            "clip_index": 0,
                            "points": [{"time": 0, "x": "system(command)"}],
                        }
                    ]
                }
            )
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_finishing(
                self.plan(
                    FinishingTools(
                        audio_regions=[
                            dict(start=0, end=2, gain_db=3),
                            dict(start=1, end=3, gain_db=2),
                        ]
                    )
                ),
                [],
            )
        with self.assertRaisesRegex(ValueError, "attached"):
            validate_finishing(
                self.plan(
                    FinishingTools(
                        layers=[
                            dict(asset_id=uuid4(), media_kind="image", start=0, end=2)
                        ]
                    )
                ),
                [],
            )

    def test_caption_region_splits_at_boundaries_and_keeps_spoken_text(self):
        tools = FinishingTools(
            caption_regions=[
                dict(start=1, end=2, position="upper"),
                dict(start=2, end=2.5, position="hidden"),
            ]
        )
        events = finish_caption_events(
            [dict(start=0, end=3, text="Real recorded words")], tools
        )
        self.assertEqual(
            [(e["start"], e["end"]) for e in events], [(0, 1), (1, 2), (2.5, 3)]
        )
        self.assertEqual(events[1]["position"], "upper")
        document = render_ass(events, width=320, height=568)
        self.assertIn("\\an8\\pos(160,80)", document)
        self.assertEqual(document.count("Real recorded words"), 3)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required"
    )
    def test_real_render_motion_colour_voice_and_keyed_circle_layer(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.mp4"
            width, height = 320, 568
            run_command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=0x203080:s={width}x{height}:r=30:d=3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=3",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    str(base),
                ],
                timeout=15,
            )
            captions = root / "captions.ass"
            captions.write_text(render_ass([], width=width, height=height))
            tools = FinishingTools(
                motions=[
                    dict(
                        clip_index=0,
                        points=[dict(time=0, zoom=1), dict(time=2, zoom=1.15, x=0.7)],
                    )
                ],
                colours=[dict(clip_index=0, saturation=1.1)],
                audio_regions=[dict(start=1, end=2, gain_db=6)],
                voice_denoise=True,
                layers=[
                    dict(
                        asset_id=uuid4(),
                        media_kind="image",
                        start=0.5,
                        end=2.5,
                        width=0.5,
                        x=0.5,
                        y=0.4,
                        shape="circle",
                        chroma_color="#00FF00",
                        animation="none",
                    )
                ],
            )
            image = Image.new("RGB", (200, 200), "#00FF00")
            ImageDraw.Draw(image).ellipse((50, 50, 150, 150), fill="red")
            image_path = root / "key.png"
            image.save(image_path)
            plan = self.plan(tools)
            output = root / "finished.mp4"
            _render_video(
                [(base, 0, 3)],
                plan,
                captions,
                output,
                30,
                width=width,
                height=height,
                picture_layers=[
                    dict(cue=tools.layers[0], path=image_path, input_index=1)
                ],
            )

            import array
            import math

            pcm = array.array(
                "f",
                subprocess.check_output(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        str(output),
                        "-vn",
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        "-f",
                        "f32le",
                        "-",
                    ]
                ),
            )

            def rms(a, b):
                samples = pcm[round(a * 96000) : round(b * 96000)]
                return math.sqrt(sum(value * value for value in samples) / len(samples))

            self.assertGreater(rms(1.2, 1.8), rms(0.2, 0.8) * 1.4)

            def frame(at):
                return subprocess.check_output(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-ss",
                        str(at),
                        "-i",
                        str(output),
                        "-frames:v",
                        "1",
                        "-f",
                        "rawvideo",
                        "-pix_fmt",
                        "rgb24",
                        "-",
                    ]
                )

            def pixel(data, x, y):
                start = (y * width + x) * 3
                return tuple(data[start : start + 3])

            before, during = frame(0.2), frame(1)
            center = pixel(during, 160, 243)
            self.assertGreater(center[0], 150)
            self.assertLess(center[1], 100)
            outside = pixel(during, 90, 178)
            self.assertGreater(outside[2], outside[1])
            self.assertLess(pixel(before, 160, 243)[0], 100)
            probe = __import__("json").loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_format",
                        "-of",
                        "json",
                        str(output),
                    ]
                )
            )
            self.assertAlmostEqual(float(probe["format"]["duration"]), 3, delta=0.1)

    def test_trim_and_duration_variant_retime_finishing_with_surviving_content(self):
        from app.edit_plan import apply_timeline_adjustments, derive_duration_variant

        plan = self.plan(
            FinishingTools(
                audio_regions=[dict(start=1, end=2.5, gain_db=3)],
                caption_regions=[dict(start=1, end=2.5, position="upper")],
                motions=[
                    dict(
                        clip_index=0,
                        points=[dict(time=0, zoom=1), dict(time=2, zoom=1.2)],
                    )
                ],
            )
        )
        trimmed = apply_timeline_adjustments(plan, [dict(clip_index=0, source_in=1)])
        self.assertEqual(trimmed.finishing.audio_regions[0].start, 0)
        self.assertEqual(trimmed.finishing.audio_regions[0].end, 1.5)
        self.assertAlmostEqual(trimmed.finishing.motions[0].points[0].zoom, 1.1)
        shorter = derive_duration_variant(plan, 2)
        self.assertEqual(shorter.finishing.caption_regions[0].end, 2)

    def test_audio_join_rejects_covering_another_spoken_phrase(self):
        from app.finishing_tools import validate_finishing

        plan = self.plan(
            FinishingTools(audio_joins=[dict(clip_index=1, lead_seconds=0.4)])
        )
        second = plan.clips[0].model_copy(deep=True)
        second.source_in = 1
        second.source_out = 3
        plan.clips[0].source_out = 1
        plan.clips.append(second)
        assets = [
            dict(
                asset_id=str(second.asset_id),
                has_audio=True,
                duration_seconds=5,
                transcript_segments=[
                    dict(words=[dict(start=0.7, end=0.95, text="still speaking")])
                ],
            )
        ]
        with self.assertRaisesRegex(ValueError, "another spoken phrase"):
            validate_finishing(plan, assets)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_real_independent_audio_join_preserves_output_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            output = root / "joined.mp4"
            captions = root / "captions.ass"
            run_command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=red:s=160x284:r=30:d=3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=3",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                timeout=10,
            )
            plan = self.plan(
                FinishingTools(
                    audio_joins=[dict(clip_index=1, lead_seconds=0.25)],
                    audio_regions=[dict(start=0.5, end=1.5, gain_db=2)],
                )
            )
            second = plan.clips[0].model_copy(deep=True)
            second.source_in = 1
            second.source_out = 3
            plan.clips[0].source_out = 1
            plan.clips.append(second)
            captions.write_text(render_ass([], width=160, height=284))
            _render_video(
                [(source, 0, 1), (source, 1, 3)],
                plan,
                captions,
                output,
                20,
                width=160,
                height=284,
            )
            data = __import__("json").loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_format",
                        "-of",
                        "json",
                        str(output),
                    ]
                )
            )
            self.assertAlmostEqual(float(data["format"]["duration"]), 3, delta=0.1)

    def test_schema_15_finishing_retains_existing_image_broll_and_provenance(self):
        from app.edit_plan import validate_edit_plan, BrollCue
        from app.finishing_renderer import finishing_manifest

        image_id = uuid4()
        plan = self.plan(
            FinishingTools(
                layers=[dict(asset_id=image_id, media_kind="image", start=0.5, end=1.5)]
            )
        )
        plan.broll = [
            BrollCue(
                asset_id=image_id,
                media_kind="image",
                source_in=0,
                source_out=0,
                start_seconds=1,
                duration_seconds=1,
                editorial_intent="A real customer review.",
            )
        ]
        assets = [
            dict(
                asset_id=str(plan.clips[0].asset_id),
                has_video=True,
                has_audio=True,
                duration_seconds=3,
                mime_type="video/mp4",
            ),
            dict(
                asset_id=str(image_id),
                mime_type="image/png",
                sha256="a" * 64,
                source_name="review.png",
            ),
        ]
        validated = validate_edit_plan(
            plan.model_dump(mode="json"),
            assets,
            creative_direction={"edit_style": "high_impact"},
        )
        self.assertEqual(len(validated.broll), 1)
        provenance = finishing_manifest({"job": {}, "assets": assets}, validated)
        self.assertEqual(provenance["picture_layers"][0]["sha256"], "a" * 64)
        self.assertFalse(provenance["picture_layers"][0]["source_audio_used"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_real_picture_dissolve_blends_frames_without_shortening_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for colour, tone in [("red", 440), ("blue", 880)]:
                path = root / f"{colour}.mp4"
                paths.append(path)
                run_command(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color={colour}:s=160x284:r=30:d=1.5",
                        "-f",
                        "lavfi",
                        "-i",
                        f"sine=frequency={tone}:duration=1.5",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-c:a",
                        "aac",
                        str(path),
                    ],
                    timeout=10,
                )
            plan = self.plan()
            plan.clips[0].source_out = 1.5
            second = plan.clips[0].model_copy(deep=True)
            second.asset_id = uuid4()
            second.transition = "cross_dissolve"
            plan.clips.append(second)
            captions = root / "captions.ass"
            captions.write_text(render_ass([], width=160, height=284))
            output = root / "dissolve.mp4"
            _render_video(
                [(path, 0, 1.5) for path in paths],
                plan,
                captions,
                output,
                20,
                width=160,
                height=284,
            )
            frame = subprocess.check_output(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    "1.6",
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-",
                ]
            )
            middle = (142 * 160 + 80) * 3
            red, green, blue = frame[middle : middle + 3]
            self.assertGreater(red, 50)
            self.assertGreater(blue, 50)
            data = __import__("json").loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_format",
                        "-of",
                        "json",
                        str(output),
                    ]
                )
            )
            self.assertAlmostEqual(float(data["format"]["duration"]), 3, delta=0.1)
