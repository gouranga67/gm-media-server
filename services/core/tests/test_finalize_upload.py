import tempfile
import unittest
from pathlib import Path

from app.finalize_upload import finalize_original, upload_source_path


class FinalizeOriginalTests(unittest.TestCase):
    def test_copies_hashes_and_removes_staging_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "asset-id"
            destination = root / "originals" / "project-id" / "asset-id" / "source"
            source.write_bytes(b"source footage")
            source.with_name("asset-id.info").write_text("{}", encoding="utf-8")

            digest = finalize_original(source, destination, len(b"source footage"))

            self.assertEqual(
                digest,
                "a2f4ac900478432999d22b04bb72c2b69268a6174d2b17534a8e8608a7fc67ab",
            )
            self.assertEqual(destination.read_bytes(), b"source footage")
            self.assertFalse(source.exists())
            self.assertFalse(source.with_name("asset-id.info").exists())

    def test_rejects_size_mismatch_without_installing_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "asset-id"
            destination = root / "originals" / "source"
            source.write_bytes(b"abc")

            with self.assertRaisesRegex(ValueError, "larger"):
                finalize_original(source, destination, 2)

            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())

    def test_recovery_reuses_installed_original_and_cleans_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "asset-id"
            destination = root / "originals" / "source"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"already durable")
            source.write_bytes(b"already durable")
            source.with_name("asset-id.info").write_text("{}", encoding="utf-8")

            digest = finalize_original(source, destination, len(b"already durable"))

            self.assertEqual(
                digest,
                "b4846795460441c6f20271edc5a8db67dc456fa9149b23b3b942f9caceffae2c",
            )
            self.assertFalse(source.exists())
            self.assertFalse(source.with_name("asset-id.info").exists())

    def test_rejects_path_like_upload_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid upload ID"):
            upload_source_path(Path("/uploads"), "../secret")


if __name__ == "__main__":
    unittest.main()
