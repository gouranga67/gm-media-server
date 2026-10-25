import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from app.asset_credits import delivery_asset_credits


class StarterLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(__file__).resolve().parents[3] / "scripts/import-creative-starter-library.py"
        if not script.exists():
            cls.importer = None  # The production test container mounts tests and app only.
            return
        spec = importlib.util.spec_from_file_location("starter_importer", script)
        cls.importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.importer)

    def test_asset_credits_include_emoji_notice_and_complete_license(self):
        asset = {"title": "Thinking face", "license_name": "Apache-2.0",
                 "license_source_url": "https://github.com/googlefonts/noto-emoji/tree/v2.047",
                 "attribution": "Copyright Google LLC. Artwork scaled and composited."}
        text = delivery_asset_credits({"creative_effects": [asset, asset]})
        self.assertIn("TERMS AND CONDITIONS", text)
        self.assertIn("Copyright Google LLC", text)
        self.assertEqual(text.count("Thinking face"), 1)

    def test_music_credits_are_carried_into_delivery(self):
        text = delivery_asset_credits({"music": {"title": "Revelation", "license_name": "CC0-1.0",
                                     "attribution": "Indieteur", "license_source_url": "https://opengameart.org/content/revelation"}})
        self.assertIn("Revelation", text)
        self.assertIn("Indieteur", text)

    def test_corrupted_download_is_rejected(self):
        if self.importer is None:
            self.skipTest("import script is covered in source CI")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.importer.checked_bytes(b"changed", hashlib.sha256(b"original").hexdigest())

    def test_cache_verifies_archive_and_selected_member(self):
        if self.importer is None:
            self.skipTest("import script is covered in source CI")
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("Audio/click.ogg", b"selected sound")
            archive.writestr("../untrusted", b"must not be extracted")
        contents = data.getvalue()
        url = "https://example.com/sounds.zip"
        item = {"download_url": url, "download_sha256": hashlib.sha256(contents).hexdigest(),
                "archive_member": "Audio/click.ogg", "sha256": hashlib.sha256(b"selected sound").hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / hashlib.sha256(url.encode()).hexdigest()).write_bytes(contents)
            self.assertEqual(self.importer.asset_bytes(item, cache), b"selected sound")
            self.assertEqual(len(list(cache.iterdir())), 1)

    def test_catalogue_contains_all_three_asset_families_and_valid_pins(self):
        if self.importer is None:
            self.skipTest("catalogue is covered in source CI")
        assets = json.loads((self.importer.ROOT / "docs/creative-starter-library.json").read_text())["assets"]
        self.assertEqual({item["kind"] for item in assets}, {"music", "sticker", "sound_effect"})
        for item in assets:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertIn(item["license_name"], {"CC0-1.0", "Apache-2.0"})
            self.assertTrue(item["license_source_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
