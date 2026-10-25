import shutil
import array
import json
import math
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
import zlib

from app.config import Settings
from app.edit_plan import CreativeEffectCue, MontageEditPlan, TalkingHeadEditPlan
from app.edit_renderer import _render_video, render_ass
from app.montage_renderer import _render as render_montage


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for the creative render test")
class CreativeRenderIntegrationTests(unittest.TestCase):
    @staticmethod
    def ffmpeg(*arguments: str) -> bytes:
        return subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
            check=True, capture_output=True, timeout=60,
        ).stdout

    def assert_rendered_content(self, output: Path, *, with_music: bool) -> None:
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output),
        ], timeout=15))
        self.assertAlmostEqual(float(probe["format"]["duration"]), 4.0, delta=0.12)
        video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"], video["pix_fmt"]), (180, 320, "yuv420p"))

        def frame(at: float) -> bytes:
            return self.ffmpeg("-ss", str(at), "-i", str(output), "-frames:v", "1",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1")

        def pixel(data: bytes, x: int, y: int) -> tuple[int, ...]:
            offset = (y * 180 + x) * 3
            return tuple(data[offset:offset + 3])

        before, sticker, after = frame(0.2), frame(0.8), frame(1.6)
        self.assertLess(max(pixel(before, 90, 55)), 20)
        red = pixel(sticker, 90, 55)
        self.assertGreater(red[0], 180, "sticker must actually be visible during its cue")
        self.assertLess(max(red[1:]), 50)
        self.assertLess(max(pixel(sticker, 45, 55)), 20,
                        "transparent sticker edges must preserve the background")
        self.assertLess(max(pixel(after, 90, 55)), 20, "sticker must disappear after its cue")
        green, blue = pixel(frame(2.6), 90, 55), pixel(frame(2.85), 90, 55)
        self.assertGreater(green[1], 180, "GIF must start at its own first animation frame")
        self.assertGreater(blue[2], 180, "GIF must animate during its cue")
        self.assertGreater(pixel(frame(3.1), 90, 55)[1], 180, "GIF must loop until its cue ends")
        self.assertLess(max(pixel(frame(3.8), 90, 55)), 20)

        def white_width(data: bytes) -> int:
            return sum(min(pixel(data, x, 150)) > 200 for x in range(180))

        self.assertGreater(white_width(frame(2.7)), white_width(before) + 3,
                           "punch-in must visibly enlarge the source")
        self.assertLess(max(pixel(frame(2.0), 90, 150)), 40,
                        "dip-to-black must darken the cut boundary")
        # Captions sit below the overlays and survive both compositing paths.
        self.assertGreater(sum(max(pixel(sticker, x, y)) > 100
                               for y in range(220, 295) for x in range(180)), 25)

        pcm = array.array("h", self.ffmpeg("-i", str(output), "-vn", "-ac", "1", "-ar", "8000",
                                          "-f", "s16le", "pipe:1"))

        def magnitude(frequency: int, start: float, end: float) -> float:
            samples = pcm[round(start * 8000):round(end * 8000)]
            real = sum(value * math.cos(2 * math.pi * frequency * index / 8000)
                       for index, value in enumerate(samples))
            imaginary = sum(value * math.sin(2 * math.pi * frequency * index / 8000)
                            for index, value in enumerate(samples))
            return math.hypot(real, imaginary) / len(samples)

        if with_music:
            self.assertGreater(magnitude(180, 0.2, 0.4), 5, "background music must be audible")
        else:
            self.assertLess(magnitude(180, 0.2, 0.4), 15, "no music should be added when it is Off")
        self.assertGreater(magnitude(440, 0.2, 0.4), 30, "source speech tone must survive the mix")
        self.assertGreater(magnitude(1000, 1.1, 1.4), 100, "sound effect must be audible at its cue")
        self.assertLess(magnitude(1000, 0.2, 0.4), 15, "sound effect must not start early")
        self.assertLess(magnitude(1000, 1.7, 1.9), 15, "sound effect must end with its cue")

    def test_real_effects_motion_and_transitions_in_both_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, music, sticker, gif, sound = [root / name for name in
                ("source.mp4", "music.wav", "sticker.png", "reaction.gif", "sound.wav")]
            self.ffmpeg("-f", "lavfi", "-i",
                        "color=c=black:s=180x320:r=30:d=4,drawbox=x=60:y=130:w=60:h=60:c=white:t=fill",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source))
            self.ffmpeg("-f", "lavfi", "-i", "sine=frequency=180:sample_rate=44100:duration=4", str(music))
            # RGBA fixture with transparent side borders, like an emoji PNG.
            def png_chunk(kind: bytes, data: bytes) -> bytes:
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

            rows = b"".join(b"\x00" + b"".join(bytes((255, 0, 0, 255 if 8 <= x < 24 else 0))
                                              for x in range(32)) for _ in range(32))
            sticker.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0))
                                + png_chunk(b"IDAT", zlib.compress(rows)) + png_chunk(b"IEND", b""))
            self.ffmpeg("-f", "lavfi", "-i", "color=c=lime:s=32x32:r=4:d=0.25",
                        "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=4:d=0.25",
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", str(gif))
            self.ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=22050:duration=1", str(sound))
            image = root / "photo.png"
            self.ffmpeg("-i", str(source), "-frames:v", "1", str(image))
            source_id, image_id, music_id = uuid4(), uuid4(), uuid4()
            effects = []
            for index, (kind, path, start, duration) in enumerate([
                ("sticker", sticker, 0.5, 0.8), ("gif", gif, 2.5, 1.0),
                ("sound_effect", sound, 1.0, 0.5),
            ], start=3):
                effect_id = uuid4()
                effects.append({"asset_id": str(effect_id), "kind": kind, "path": path,
                    "_storage_key": path.name, "input_index": index,
                    "cue": CreativeEffectCue(asset_id=effect_id, start_seconds=start,
                        duration_seconds=duration, position="top", intensity="strong")})
            common = dict(schema_version="1.3", end_card="none", editorial_summary="Rendered content verification.",
                          music_track_id=music_id, music_mix="subtle", effects=[item["cue"] for item in effects])
            clips = [dict(asset_id=source_id, source_in=0, source_out=2, crop="center_fill", visual_preset="standard"),
                     dict(asset_id=source_id, source_in=2, source_out=4, crop="center_fill",
                          visual_preset="punch_in", transition="dip_to_black")]
            captions = root / "captions.ass"
            captions.write_text(render_ass([{"start": 0, "end": 4, "text": "Test captions"}],
                                           width=180, height=320), encoding="utf-8")
            settings = Settings(database_url="postgresql://unused", upload_hook_secret="x" * 32, media_root=root)
            context = {"assets": [{"asset_id": str(source_id), "_storage_key": source.name, "has_audio": True},
                                  {"asset_id": str(image_id), "_storage_key": image.name, "has_audio": False}],
                       "music_library": [{"track_id": str(music_id), "_storage_key": music.name}],
                       "creative_effect_library": effects}
            for recipe, with_music in [(recipe, enabled) for recipe in ("talking_head", "montage")
                                       for enabled in (True, False)]:
                with self.subTest(recipe=recipe, with_music=with_music):
                    output = root / f"{recipe}-{with_music}.mp4"
                    values = {**common, "music_track_id": music_id if with_music else None,
                              "music_mix": "subtle" if with_music else "none"}
                    if recipe == "talking_head":
                        plan = TalkingHeadEditPlan(**values, recipe=recipe, clips=clips,
                                                  caption_style="clean_blue_v1", audio_preset="spoken_voice_v1")
                        _render_video([(source, 0, 2), (source, 2, 4)], plan, captions, output, 60,
                                      width=180, height=320, music_source=music if with_music else None,
                                      effect_sources=[{**item, "input_index": index}
                                                      for index, item in enumerate(effects, start=3 if with_music else 2)])
                    else:
                        montage_clips = [dict(**clip, duration=2, media_kind="video", include_source_audio=True)
                                         for clip in clips]
                        montage_clips[1].update(asset_id=image_id, media_kind="image",
                                               source_in=0, source_out=0, include_source_audio=False)
                        plan = MontageEditPlan(**values, recipe=recipe, audio_preset="montage_mix_v1",
                                               clips=montage_clips)
                        render_montage(context, plan, output, width=180, height=320, final=True,
                                       settings=settings, captions_path=captions)
                    self.assert_rendered_content(output, with_music=with_music)

    def test_renders_motion_transition_and_ducked_music(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            music = root / "music.wav"
            captions = root / "captions.ass"
            output = root / "output.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=180x320:rate=30:duration=4",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(source),
                ],
                check=True,
                timeout=60,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=180:sample_rate=48000:duration=4",
                    str(music),
                ],
                check=True,
                timeout=60,
            )
            asset_id = uuid4()
            plan = TalkingHeadEditPlan.model_validate(
                {
                    "schema_version": "1.1",
                    "recipe": "talking_head",
                    "clips": [
                        {
                            "asset_id": str(asset_id),
                            "source_in": 0,
                            "source_out": 2,
                            "crop": "center_fill",
                            "transition": "cut",
                            "visual_preset": "standard",
                        },
                        {
                            "asset_id": str(asset_id),
                            "source_in": 2,
                            "source_out": 4,
                            "crop": "center_fill",
                            "transition": "dip_to_black",
                            "visual_preset": "slow_push_in",
                        },
                    ],
                    "caption_style": "clean_blue_v1",
                    "audio_preset": "spoken_voice_v1",
                    "end_card": "none",
                    "editorial_summary": "Creative renderer integration test.",
                    "post_copy": "",
                    "music_track_id": str(uuid4()),
                    "music_mix": "subtle",
                }
            )
            captions.write_text(
                render_ass([{"start": 0, "end": 3.5, "text": "Creative test"}], width=180, height=320),
                encoding="utf-8",
            )

            encoder = _render_video(
                [(source, 0, 2), (source, 2, 4)],
                plan,
                captions,
                output,
                120,
                width=180,
                height=320,
                frames_per_second=30,
                music_source=music,
            )

            self.assertIn(encoder, {"h264_nvenc", "libx264"})
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
