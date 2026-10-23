import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.edit_plan import TalkingHeadEditPlan
from app.edit_renderer import _render_video, render_ass


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for the creative render test")
class CreativeRenderIntegrationTests(unittest.TestCase):
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
