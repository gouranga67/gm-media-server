"""Rendered edge-marker checks for stills: text-bearing images must not be cropped."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.edit_plan import BrollCue, TalkingHeadEditPlan
from app.edit_renderer import _render_video, render_ass
from app.finishing_renderer import append_broll_filters, image_broll_layout, public_broll_manifest
from app.media_analysis import run_command


def image_cue(asset_id=None):
    return BrollCue(asset_id=asset_id or uuid4(), media_kind="image", source_in=0, source_out=0,
                    start_seconds=0.5, duration_seconds=1, editorial_intent="Show the complete review.")


class ImageBrollTests(unittest.TestCase):
    def test_images_contain_and_keep_alpha_while_video_retains_fill(self):
        cue = image_cue()
        graph = append_broll_filters("[base]null[vout];[voice]anull[aout]", [{"cue": cue, "input_index": 1}], width=540, height=960, fps=30)
        self.assertIn("force_original_aspect_ratio=decrease", graph)
        self.assertIn("format=rgba", graph)
        self.assertNotIn("crop=", graph)
        self.assertIn("drawbox=", graph)
        self.assertIn("[voice]anull[aout]", graph)
        self.assertIn("gte(t,0.500)*lt(t,1.500)", graph)
        video = cue.model_copy(update={"media_kind": "video", "source_out": 1})
        graph = append_broll_filters("[base]null[vout]", [{"cue": video, "input_index": 1}], width=540, height=960, fps=30)
        self.assertIn("force_original_aspect_ratio=increase,crop=540:960", graph)
        self.assertNotIn("drawbox=", graph)

    def test_image_bounds_leave_the_lower_caption_band_clear_at_all_output_sizes(self):
        for width, height in ((540, 960), (1080, 1920), (1080, 1080), (1920, 1080)):
            with self.subTest(size=(width, height)):
                box = image_broll_layout(width, height)
                self.assertEqual(box["max_width"] % 2, 0)
                self.assertEqual(box["max_height"] % 2, 0)
                self.assertGreaterEqual(box["center_y"] - box["max_height"] / 2, 0)
                self.assertLess(box["center_y"] + box["max_height"] / 2, height * 0.70)

    def test_card_position_moves_clear_of_upper_and_middle_captions(self):
        upper = image_broll_layout(540, 960, "upper")
        middle = image_broll_layout(540, 960, "middle")
        self.assertGreater(upper["center_y"] - upper["max_height"] / 2, 960 * 0.30)
        self.assertLess(middle["center_y"] + middle["max_height"] / 2, 960 * 0.42)

    def test_manifest_explains_still_framing_and_keeps_timing_and_source_identity(self):
        cue = image_cue()
        plan = TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head", caption_style="clean_blue_v1",
                                   audio_preset="spoken_voice_v1", end_card="none", clips=[dict(asset_id=uuid4(), source_in=0, source_out=2, crop="center_fill")],
                                   editorial_summary="Keep the story.", broll=[cue])
        record = public_broll_manifest({"assets": [{"asset_id": str(cue.asset_id), "source_name": "review.png", "sha256": "source-checksum"}]}, plan)[0]
        self.assertEqual(record["framing"], "contain_card_v1")
        self.assertFalse(record["source_cropped"])
        self.assertFalse(record["source_audio_used"])
        self.assertEqual(record["start_seconds"], cue.start_seconds)
        self.assertEqual(record["sha256"], "source-checksum")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_real_render_keeps_all_four_edges_and_transparency_without_changing_speech(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            width, height = 320, 568
            base = root / "base.mp4"
            run_command(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", f"color=0x203080:s={width}x{height}:r=30:d=2",
                         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(base)], timeout=15)
            captions = root / "captions.ass"
            captions.write_text(render_ass([dict(start=0, end=2, text="Speech continues")], width=width, height=height))
            image_id = uuid4()
            cue = image_cue(image_id)
            plan = TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head", caption_style="clean_blue_v1",
                                   audio_preset="spoken_voice_v1", end_card="none", clips=[dict(asset_id=uuid4(), source_in=0, source_out=2, crop="center_fill")],
                                       editorial_summary="Keep continuous speech.", broll=[cue])
            baseline = root / "baseline.mp4"
            _render_video([(base, 0, 2)], plan, captions, baseline, 30, width=width, height=height)
            def decode(path, *, time=1):
                return subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(time), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
            def pixel(frame, x, y):
                at = (y * width + x) * 3
                return tuple(frame[at:at + 3])
            def audio(path):
                return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-"])
            baseline_audio = audio(baseline)
            baseline_frame = decode(baseline)
            box = image_broll_layout(width, height)
            for source_size, alpha in (((480, 360), False), ((180, 480), False), ((480, 360), True)):
                with self.subTest(size=source_size, alpha=alpha):
                    iw, ih = source_size
                    image = Image.new("RGBA" if alpha else "RGB", source_size, (0, 0, 0, 0) if alpha else "white")
                    draw = ImageDraw.Draw(image)
                    border = 24
                    draw.rectangle((0, 0, iw - 1, border), fill="red")
                    draw.rectangle((0, ih - border, iw - 1, ih - 1), fill="lime")
                    draw.rectangle((0, border, border, ih - border), fill="blue")
                    draw.rectangle((iw - border, border, iw - 1, ih - border), fill="yellow")
                    source = root / "review.png"; image.save(source)
                    output = root / f"overlay-{iw}-{alpha}.mp4"
                    _render_video([(base, 0, 2)], plan, captions, output, 30, width=width, height=height,
                                  broll_sources=[dict(cue=cue, path=source, input_index=1)])
                    frame = decode(output)
                    ratio = min(box["max_width"] / iw, box["max_height"] / ih)
                    fw, fh = int(iw * ratio) // 2 * 2, int(ih * ratio) // 2 * 2
                    x, y = (width - fw) // 2, box["center_y"] - fh // 2
                    dx, dy = max(2, round(12 * fw / iw)), max(2, round(12 * fh / ih))
                    samples = [(width // 2, y + dy, (255, 0, 0)), (width // 2, y + fh - dy, (0, 255, 0)),
                               (x + dx, box["center_y"], (0, 0, 255)), (x + fw - dx, box["center_y"], (255, 255, 0))]
                    for px, py, expected in samples:
                        actual = pixel(frame, px, py)
                        self.assertTrue(all(abs(a - b) < 65 for a, b in zip(actual, expected)), (actual, expected))
                    if alpha:
                        # The center hole reveals dimmed blue footage, not an opaque black rectangle.
                        center = pixel(frame, width // 2, box["center_y"])
                        outside = pixel(frame, 4, box["center_y"])
                        self.assertTrue(all(abs(a - b) < 10 for a, b in zip(center, outside)), (center, outside))
                        self.assertGreater(center[2], 10)
                    self.assertEqual(audio(output), baseline_audio)
                    for time in (0.1, 1.8):
                        outside_cue = decode(output, time=time)
                        for px, py in ((20, 30), (width // 2, box["center_y"]), (width // 2, y + dy)):
                            self.assertTrue(all(abs(a - b) < 12 for a, b in zip(pixel(outside_cue, px, py), pixel(baseline_frame, px, py))))
                    # Captions still render in the unobscured lower part of the picture.
                    caption_band = frame[int(height * 0.65) * width * 3:]
                    self.assertGreater(sum(value > 200 for value in caption_band), 50)
