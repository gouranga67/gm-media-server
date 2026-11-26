import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from app import google_drive as drive


class Secret:
    def __init__(self, value):
        self.value = value

    def get_secret_value(self):
        return self.value


def settings():
    return SimpleNamespace(
        google_drive_enabled=True,
        google_drive_client_id="123-example.apps.googleusercontent.com",
        google_drive_client_secret=Secret("client-secret"),
        google_drive_token_encryption_key=Secret(Fernet.generate_key().decode()),
        google_drive_api_key=Secret("picker-key"),
        google_drive_app_id="123",
        google_drive_app_origin="https://studio.example.invalid",
    )


class Response(BytesIO):
    def __init__(self, value, status=200):
        super().__init__(value)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class GoogleDriveTransportTests(unittest.TestCase):
    def test_authorization_uses_narrow_scope_and_exact_callback(self):
        url = drive.authorization_url(settings(), "safe-state")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["scope"], [drive.DRIVE_SCOPE])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["redirect_uri"], ["https://studio.example.invalid/api/media/google-drive/callback"])
        self.assertEqual(query["state"], ["safe-state"])

    def test_refresh_tokens_are_encrypted_and_wrong_keys_require_reconnect(self):
        config = settings()
        encrypted = drive.encrypt_refresh_token(config, "private-refresh-token")
        self.assertNotIn("private-refresh-token", encrypted)
        self.assertEqual(drive.decrypt_refresh_token(config, encrypted), "private-refresh-token")
        with self.assertRaisesRegex(drive.GoogleDriveError, "Reconnect") as caught:
            drive.decrypt_refresh_token(settings(), encrypted)
        self.assertTrue(caught.exception.reconnect)

    def test_download_resumes_with_range_and_keeps_bounded_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "drive-file"
            destination.write_bytes(b"abc")
            values = []
            with patch.object(drive, "urlopen", return_value=Response(b"def", 206)) as fetch:
                drive.download_file("access", "safe-file_id", destination, 6, values.append)
            self.assertEqual(destination.read_bytes(), b"abcdef")
            self.assertEqual(fetch.call_args.args[0].headers["Range"], "bytes=3-")
            self.assertEqual(values[-1], 6)

    def test_invalid_remote_identifier_never_reaches_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(drive, "urlopen") as fetch:
            with self.assertRaisesRegex(drive.GoogleDriveError, "invalid"):
                drive.download_file("access", "../../secret", Path(directory) / "file", 10)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
