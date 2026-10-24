import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.main import app
from app.productization import MemberCreate, _safe_unlink, normalize_login


class ProductizationTests(unittest.TestCase):
    def test_tailscale_login_is_normalized(self) -> None:
        self.assertEqual(normalize_login("  Person@Example.COM "), "person@example.com")

    def test_member_requires_email_shaped_tailscale_login(self) -> None:
        with self.assertRaises(ValidationError):
            MemberCreate(login="friendly-name", role="viewer")

    def test_retention_unlinks_only_resolved_file_and_reports_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "exports" / "preview.mp4"
            target.parent.mkdir()
            target.write_bytes(b"derived")
            self.assertEqual(_safe_unlink(root, "exports/preview.mp4"), 7)
            self.assertFalse(target.exists())

    def test_retention_refuses_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ValueError, FileNotFoundError)):
                _safe_unlink(Path(directory), "../outside")

    def test_job_manager_route_precedes_generic_job_lookup(self) -> None:
        get_paths = [
            route.path
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        ]
        self.assertLess(
            get_paths.index("/api/v1/jobs/manage"),
            get_paths.index("/api/v1/jobs/{job_id}"),
        )


if __name__ == "__main__":
    unittest.main()
