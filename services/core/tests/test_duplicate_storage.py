import tempfile
import unittest
from pathlib import Path

from app.duplicate_storage import share_exact_duplicate_storage


class DuplicateStorageTests(unittest.TestCase):
    def test_exact_copy_becomes_shared_storage_without_changing_paths(self) -> None:
        payload = b"verified original bytes" * 1024
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "canonical"
            duplicate = root / "duplicate"
            canonical.write_bytes(payload)
            duplicate.write_bytes(payload)
            result = share_exact_duplicate_storage(
                canonical,
                duplicate,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                expected_size=len(payload),
            )
            self.assertEqual(canonical.read_bytes(), payload)
            self.assertEqual(duplicate.read_bytes(), payload)
            self.assertEqual(canonical.stat().st_ino, duplicate.stat().st_ino)
            self.assertEqual(result.bytes_reclaimed, len(payload))
            self.assertFalse(result.already_shared)
            repeated = share_exact_duplicate_storage(
                canonical,
                duplicate,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                expected_size=len(payload),
            )
            self.assertTrue(repeated.already_shared)
            self.assertEqual(repeated.bytes_reclaimed, 0)

    def test_mismatched_copy_is_never_replaced(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "canonical"
            duplicate = root / "duplicate"
            canonical.write_bytes(b"correct")
            duplicate.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                share_exact_duplicate_storage(
                    canonical,
                    duplicate,
                    expected_sha256=hashlib.sha256(b"correct").hexdigest(),
                    expected_size=len(b"correct"),
                )
            self.assertEqual(duplicate.read_bytes(), b"changed")
            self.assertNotEqual(canonical.stat().st_ino, duplicate.stat().st_ino)


if __name__ == "__main__":
    unittest.main()
