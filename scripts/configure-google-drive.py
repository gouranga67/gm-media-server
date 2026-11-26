#!/usr/bin/env python3
"""Configure Google Drive import without printing secrets or OAuth tokens."""

import base64
import getpass
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / ".env"
    if path.is_symlink() or not path.is_file():
        raise SystemExit("Use an existing regular .env file in the project directory.")
    source = path.read_text()
    values = {}
    for line in source.splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    origin = values.get("APP_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("APP_ORIGIN must be the HTTPS studio origin without a path.")
    print("This configures explicit Google Drive file selection. It does not connect an account yet.")
    print("First enable Google Drive API and Google Picker API in one Google Cloud project.")
    client_id = input(f"OAuth web client ID [{values.get('GOOGLE_DRIVE_CLIENT_ID', '')}]: ").strip() or values.get("GOOGLE_DRIVE_CLIENT_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.apps\.googleusercontent\.com", client_id):
        raise SystemExit("Enter the OAuth web client ID ending in .apps.googleusercontent.com.")
    client_secret = getpass.getpass("OAuth client secret (hidden; Enter keeps existing): ").strip() or values.get("GOOGLE_DRIVE_CLIENT_SECRET", "")
    if len(client_secret) < 10 or any(character.isspace() for character in client_secret):
        raise SystemExit("The OAuth client secret is invalid.")
    api_key = getpass.getpass("Google Picker API key (hidden; Enter keeps existing): ").strip() or values.get("GOOGLE_DRIVE_API_KEY", "")
    if len(api_key) < 20 or any(character.isspace() for character in api_key):
        raise SystemExit("The Google Picker API key is invalid.")
    app_id = input(f"Google Cloud project number [{values.get('GOOGLE_DRIVE_APP_ID', '')}]: ").strip() or values.get("GOOGLE_DRIVE_APP_ID", "")
    if not app_id.isdigit():
        raise SystemExit("The Google Cloud project number must contain digits only.")
    encryption_key = values.get("GOOGLE_DRIVE_TOKEN_ENCRYPTION_KEY") or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    try:
        if len(base64.urlsafe_b64decode(encryption_key)) != 32:
            raise ValueError("key")
    except (TypeError, ValueError):
        raise SystemExit("The existing Drive encryption key is invalid. Restore it rather than replacing it after accounts are connected.")
    updates = {
        "GOOGLE_DRIVE_ENABLED": "true",
        "GOOGLE_DRIVE_CLIENT_ID": client_id,
        "GOOGLE_DRIVE_CLIENT_SECRET": client_secret,
        "GOOGLE_DRIVE_TOKEN_ENCRYPTION_KEY": encryption_key,
        "GOOGLE_DRIVE_API_KEY": api_key,
        "GOOGLE_DRIVE_APP_ID": app_id,
    }
    lines = [line for line in source.splitlines() if line.partition("=")[0].strip() not in updates]
    lines += ["", "# Google Drive import: keep these values private and preserve the encryption key."] + [f"{key}={value}" for key, value in updates.items()]
    descriptor, temporary = tempfile.mkstemp(prefix=".env-google-drive-", dir=root)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Saved Google Drive settings privately. No account token was created or displayed.")
    print("Register this exact authorized JavaScript origin: " + origin)
    print("Register this exact OAuth redirect URI: " + origin + "/api/media/google-drive/callback")
    print("Next: redeploy GM Studio, then open Library → Add media → Google Drive → Connect Google Drive.")


if __name__ == "__main__":
    main()
