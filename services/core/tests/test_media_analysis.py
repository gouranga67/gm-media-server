import json
import tempfile
import unittest
from pathlib import Path

from app.media_analysis import (
    atomic_write,
    format_vtt_timestamp,
    normalize_probe,
    render_webvtt,
    resolve_source,
)


class ResolveSourceTests(unittest.TestCase):
    def test_resolves_a_file_inside_the_media_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "originals" / "project" / "asset" / "source"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"media")

            self.assertEqual(resolve_source(root, "originals/project/asset/source"), source)

    def test_rejects_traversal_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media"
            outside = Path(directory) / "secret"
            root.mkdir()
            outside.write_bytes(b"secret")
            (root / "link").symlink_to(outside)

            with self.assertRaises(ValueError):
                resolve_source(root, "../secret")
            with self.assertRaises(ValueError):
                resolve_source(root, "link")


class ProbeNormalizationTests(unittest.TestCase):
    def test_keeps_technical_fields_and_drops_embedded_metadata(self) -> None:
        payload = {
            "format": {
                "format_name": "mov,mp4",
                "duration": "12.5",
                "size": "1234",
                "bit_rate": "789",
                "tags": {"location": "private", "comment": "do not expose"},
            },
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "duration": "12.467",
                    "r_frame_rate": "30000/1001",
                    "side_data_list": [{"rotation": -90}],
                    "tags": {"title": "private"},
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "duration": "12.500",
                },
            ],
        }

        result = normalize_probe(payload)

        self.assertEqual(result["format"]["duration_seconds"], 12.5)
        self.assertEqual(result["streams"][0]["frames_per_second"], 29.97)
        self.assertEqual(result["streams"][0]["rotation_degrees"], -90)
        self.assertEqual(result["streams"][0]["duration_seconds"], 12.467)
        self.assertEqual(result["streams"][1]["duration_seconds"], 12.5)
        self.assertNotIn("tags", json.dumps(result))
        self.assertNotIn("private", json.dumps(result))


class TranscriptOutputTests(unittest.TestCase):
    def test_formats_long_timestamps_and_webvtt(self) -> None:
        self.assertEqual(format_vtt_timestamp(3661.234), "01:01:01.234")
        output = render_webvtt(
            [{"start": 0.25, "end": 2.0, "text": " First line. "}]
        )
        self.assertEqual(
            output,
            "WEBVTT\n\n1\n00:00:00.250 --> 00:00:02.000\nFirst line.\n",
        )

    def test_atomic_write_replaces_partial_output_as_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis" / "manifest.json"
            atomic_write(path, '{"ready": true}\n')

            self.assertEqual(path.read_text(encoding="utf-8"), '{"ready": true}\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o440)
            self.assertFalse(path.with_name(".manifest.json.part").exists())


if __name__ == "__main__":
    unittest.main()
