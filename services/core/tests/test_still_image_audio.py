"""An extensionless photo must never reset the shared speech/music clock."""

import array
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan, BrollCue, CreativeEffectCue
from app.edit_renderer import _render_video, render_ass
from app.effect_renderer import effect_input_arguments
from app.finishing_renderer import broll_input_arguments
from app.finishing_tools import PictureLayer, picture_layer_inputs
from app.media_analysis import run_command, still_image_input_arguments
from app.render_integrity import rendered_audio_packet_error
from test_camera_timing import make_source, WIDTH, HEIGHT


class StillImageInputTests(unittest.TestCase):
    def test_all_still_picture_routes_use_literal_image_demuxing(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "literal%photo"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        cue = BrollCue(asset_id=uuid4(), media_kind="image", source_in=0, source_out=0,
            start_seconds=1, duration_seconds=2, editorial_intent="Reference picture")
        layer = PictureLayer(asset_id=uuid4(), media_kind="image", start=1, end=3)
        for args in (still_image_input_arguments(path, loop=False),
                     broll_input_arguments([dict(cue=cue, path=path)]),
                     picture_layer_inputs([dict(cue=layer, path=path)]),
                     effect_input_arguments([dict(kind="sticker", path=path)])):
            self.assertEqual(args[:4], ["-f", "image2", "-pattern_type", "none"])
            self.assertEqual(args[-2:], ["-i", str(path)])
        # Animation timing remains controlled by the GIF demuxer.
        self.assertNotIn("image2", effect_input_arguments([dict(kind="gif", path=path)]))
        path.write_bytes(b"\x00\x00\x00\x20ftypavif")
        self.assertNotIn("image2", still_image_input_arguments(path))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class StillImageAudioTests(unittest.TestCase):
    def test_embedded_jpeg_with_changed_dimensions_keeps_speech_pulses_after_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "moving.mkv"
            make_source(source, 30, audio_offset=0.09)
            images = []
            for index, size in enumerate(("96x128", "64x64")):
                path = root / f"image-{index}.jpg"
                run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=yellow:s={size}", "-frames:v", "1", str(path)], timeout=20)
                images.append(path.read_bytes())
            # Pipe demuxing interprets embedded JPEG data as a new frame and
            # reconfigures the whole graph. Literal image2 reads one still.
            image = root / "source"
            image.write_bytes(b"".join(images))
            music = root / "music.wav"
            run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "sine=frequency=120:sample_rate=44100:duration=6", "-af", "volume=0.01", str(music)], timeout=20)
            effect = root / "ding.wav"
            run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "sine=frequency=2400:duration=0.1", str(effect)], timeout=20)
            asset_id = uuid4()
            broll = BrollCue(asset_id=uuid4(), media_kind="image", source_in=0, source_out=0,
                start_seconds=0.4, duration_seconds=1, editorial_intent="Reference")
            cue = CreativeEffectCue(asset_id=uuid4(), start_seconds=2.2, duration_seconds=0.1, purpose="emphasis")
            plan = TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head",
                clips=[dict(asset_id=asset_id, source_in=0, source_out=2.8, crop="center_fill"),
                       dict(asset_id=asset_id, source_in=0, source_out=2.8, crop="center_fill", transition="cross_dissolve")],
                caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none",
                editorial_summary="Synthetic speech-clock regression", music_track_id=uuid4(), music_mix="present",
                broll=[broll], effects=[cue])
            captions = root / "empty.ass"
            captions.write_text(render_ass([], width=WIDTH, height=HEIGHT))
            output = root / "result.mp4"
            _render_video([(source, 0, 2.8)] * 2, plan, captions, output, 60, width=WIDTH, height=HEIGHT,
                music_source=music, effect_sources=[dict(kind="sound_effect", cue=cue, path=effect, input_index=3)],
                broll_sources=[dict(cue=broll, path=image, input_index=4)], safe_speech_joins=True)
            self.assertIsNone(rendered_audio_packet_error(output, 10))
            pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1",
                "-ar", "48000", "-f", "f32le", "-"], timeout=20)
            samples = array.array("f", pcm)

            def rms(at):
                block = samples[round(at * 48000):round((at + 0.03) * 48000)]
                return math.sqrt(sum(x*x for x in block) / len(block))

            for start in (0, 2.8):
                for pulse in (0.64, 1.14, 1.64, 2.64):
                    self.assertGreater(rms(start + pulse), rms(start + pulse - 0.2) * 3)
            self.assertEqual(image.read_bytes(), b"".join(images))
