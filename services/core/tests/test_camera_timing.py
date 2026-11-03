"""Temporal colour markers and audio pulses catch speed errors hidden by padding."""

import array
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan
from app.edit_renderer import _clip_video_filter, _render_video, render_ass
from app.montage_renderer import _video_filter, _render
from app.media_analysis import probe_media, run_command
from app.finishing_renderer import finishing_manifest

WIDTH, HEIGHT = 96, 128
COLOURS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (0, 255, 255),
    (255, 0, 255),
]


def make_source(path, rate, *, variable=False, audio_offset=0):
    colours = ["red", "lime", "blue", "yellow", "cyan", "magenta"]
    filters = [
        f"drawbox=c={colour}:t=fill:enable='gte(t,{index / 2})*lt(t,{(index + 1) / 2})'"
        for index, colour in enumerate(colours)
    ]
    if variable:
        # 30fps in the first half, 60fps in the second; keep original PTS.
        filters.append("select='if(lt(t,1.5),not(mod(n,2)),1)'")
    run_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=black:s={WIDTH}x{HEIGHT}:r={rate}:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=48000:duration=3",
            "-vf",
            ",".join(filters),
            "-af",
            "volume='if(lt(mod(t,0.5),0.12),1,0)':eval=frame"
            + f",asetpts=PTS+{audio_offset}/TB",
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "12",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        timeout=20,
    )


def decode_video(path):
    return subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        timeout=20,
    )


def assert_time_markers(case, pixels, *, source_offset=0):
    frame_bytes = WIDTH * HEIGHT * 3
    case.assertEqual(len(pixels) % frame_bytes, 0)
    count = len(pixels) // frame_bytes
    for frame_index in (6, 21, 36, 51, 66, 81):
        if frame_index >= count:
            continue
        expected = COLOURS[int((source_offset + frame_index / 30) * 2)]
        # The center stays inside every supported camera crop. A full-frame
        # time marker is unchanged by magnification and exposes time drift.
        offset = frame_index * frame_bytes + (HEIGHT // 2 * WIDTH + WIDTH // 2) * 3
        actual = tuple(pixels[offset : offset + 3])
        case.assertTrue(
            all(abs(a - b) < 45 for a, b in zip(actual, expected)),
            (frame_index / 30, actual, expected),
        )


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required"
)
class CameraTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.sources = {}
        for rate in (24, 25, 30, 50, 60, 120, "30000/1001", "60000/1001"):
            path = cls.root / (str(rate).replace("/", "-") + ".mkv")
            make_source(path, rate)
            cls.sources[str(rate)] = path
        path = cls.root / "variable.mkv"
        make_source(path, 60, variable=True)
        cls.sources["variable"] = path

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_video_camera_presets_preserve_source_time_at_all_input_rates(self):
        for rate, source in self.sources.items():
            for recipe in ("talking_head", "montage"):
                presets = [
                    "standard",
                    "punch_in",
                    "slow_push_in",
                    "slow_pull_out",
                    "rhythmic_punch",
                ]
                if recipe == "talking_head":
                    presets.append("strong_punch_in")
                for preset in presets:
                    with self.subTest(rate=rate, recipe=recipe, preset=preset):
                        if recipe == "talking_head":
                            graph = _clip_video_filter(
                                index=0,
                                duration=2.5,
                                visual_preset=preset,
                                fade_in=False,
                                fade_out=False,
                                width=WIDTH,
                                height=HEIGHT,
                                frames_per_second=30,
                            )
                        else:
                            graph = _video_filter(
                                0, 2.5, preset, False, False, False, WIDTH, HEIGHT, 30
                            )
                        result = subprocess.check_output(
                            [
                                "ffmpeg",
                                "-v",
                                "error",
                                "-ss",
                                "0.25",
                                "-i",
                                str(source),
                                "-filter_complex_threads",
                                "1",
                                "-filter_complex",
                                graph,
                                "-map",
                                "[v0]",
                                "-an",
                                "-f",
                                "rawvideo",
                                "-pix_fmt",
                                "rgb24",
                                "-",
                            ],
                            timeout=20,
                        )
                        self.assertEqual(len(result) // (WIDTH * HEIGHT * 3), 75)
                        assert_time_markers(self, result, source_offset=0.25)

    def test_finished_preview_and_export_keep_picture_and_audio_pulses_aligned(self):
        for recipe in ("talking_head", "montage"):
            first, second = str(uuid4()), str(uuid4())
            assets = [
                {
                    "asset_id": first,
                    "has_video": True,
                    "has_audio": True,
                    "mime_type": "video/mp4",
                },
                {
                    "asset_id": second,
                    "has_video": True,
                    "has_audio": True,
                    "mime_type": "video/mp4",
                },
            ]
            context = {
                "job": {"music_mode": "none"},
                "assets": assets,
                "music_library": [],
                "creative_effect_library": [],
            }
            document = {
                "schema_version": "1.4",
                "recipe": recipe,
                "end_card": "none",
                "editorial_summary": "Mixed-rate footage retains original picture and voice timing.",
                "clips": [
                    {
                        "asset_id": first,
                        "source_in": 0,
                        "source_out": 1.5,
                        "crop": "center_fill",
                    },
                    {
                        "asset_id": second,
                        "source_in": 1.5,
                        "source_out": 3,
                        "crop": "center_fill",
                    },
                ],
            }
            if recipe == "talking_head":
                document.update(
                    caption_style="clean_blue_v1", audio_preset="spoken_voice_v1"
                )
                model = TalkingHeadEditPlan
            else:
                document["audio_preset"] = "montage_mix_v1"
                for clip in document["clips"]:
                    clip.update(
                        media_kind="video", duration=1.5, include_source_audio=True
                    )
                model = MontageEditPlan
            source_paths = {first: self.sources["60"], second: self.sources["24"]}
            for final in (False, True):
                baseline_audio = None
                for preset in (
                    "standard",
                    "rhythmic_punch",
                    "slow_push_in",
                    "keyframes",
                ):
                    with self.subTest(recipe=recipe, final=final, preset=preset):
                        for clip in document["clips"]:
                            clip["visual_preset"] = (
                                "standard" if preset == "keyframes" else preset
                            )
                        if preset == "keyframes":
                            document["schema_version"] = "1.5"
                            document["finishing"] = {
                                "motions": [
                                    {
                                        "clip_index": index,
                                        "points": [
                                            {"time": 0, "zoom": 1},
                                            {"time": 1.5, "zoom": 1.15},
                                        ],
                                    }
                                    for index in (0, 1)
                                ]
                            }
                        else:
                            document.pop("finishing", None)
                        plan = model.model_validate(document)
                        before = plan.model_dump(mode="json")
                        output = self.root / f"{recipe}-{final}-{preset}.mp4"
                        captions = self.root / "empty.ass"
                        captions.write_text(render_ass([], width=WIDTH, height=HEIGHT))
                        if recipe == "talking_head":
                            _render_video(
                                [
                                    (
                                        source_paths[str(c.asset_id)],
                                        c.source_in,
                                        c.source_out,
                                    )
                                    for c in plan.clips
                                ],
                                plan,
                                captions,
                                output,
                                30,
                                width=WIDTH,
                                height=HEIGHT,
                                final_quality=final,
                            )
                        else:
                            with patch(
                                "app.montage_renderer._render_source",
                                side_effect=lambda settings,
                                asset,
                                **kwargs: source_paths[asset["asset_id"]],
                            ):
                                _render(
                                    context,
                                    plan,
                                    output,
                                    width=WIDTH,
                                    height=HEIGHT,
                                    final=final,
                                    settings=SimpleNamespace(
                                        analysis_command_timeout_seconds=30
                                    ),
                                    captions_path=captions,
                                )
                        self.assertEqual(plan.model_dump(mode="json"), before)
                        self.assertEqual(
                            finishing_manifest(context, plan)["video_timing_pipeline"],
                            "source_timestamps_before_camera_effects_v1",
                        )
                        self.assertAlmostEqual(
                            probe_media(output, 10)["format"]["duration_seconds"],
                            3,
                            delta=0.1,
                        )
                        assert_time_markers(self, decode_video(output))
                        raw = subprocess.check_output(
                            [
                                "ffmpeg",
                                "-v",
                                "error",
                                "-i",
                                str(output),
                                "-vn",
                                "-ac",
                                "1",
                                "-ar",
                                "48000",
                                "-f",
                                "s16le",
                                "-",
                            ],
                            timeout=20,
                        )
                        if baseline_audio is None:
                            baseline_audio = raw
                        else:
                            self.assertEqual(
                                raw,
                                baseline_audio,
                                "Camera presets must not change audio samples.",
                            )
                        samples = array.array("h", raw)

                        def rms(start, end):
                            values = samples[round(start * 48000) : round(end * 48000)]
                            return math.sqrt(
                                sum(v * v for v in values) / max(1, len(values))
                            )

                        for at in (0.5, 1, 1.5, 2, 2.5):
                            self.assertGreater(rms(at + 0.03, at + 0.08), 500)
                            self.assertLess(rms(at + 0.25, at + 0.30), 100)

    def test_still_image_zoom_expands_one_frame_for_the_requested_time(self):
        from PIL import Image

        image = self.root / "still.png"
        Image.new("RGB", (WIDTH, HEIGHT), "cyan").save(image)
        graph = _video_filter(
            0, 2, "slow_push_in", True, False, False, WIDTH, HEIGHT, 30
        )
        result = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(image),
                "-filter_complex",
                graph,
                "-map",
                "[v0]",
                "-fps_mode",
                "passthrough",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            timeout=20,
        )
        self.assertEqual(len(result) // (WIDTH * HEIGHT * 3), 60)
