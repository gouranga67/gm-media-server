#!/usr/bin/env python3
"""Configure the local Meta app without printing app secrets or account tokens."""

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
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    print(
        "This configures your Meta developer app. It does not connect accounts or publish anything."
    )
    print(
        "Create a Meta app with Facebook Login for Business and publishing permissions first."
    )
    app_id = input(
        f"Meta app ID [{values.get('META_APP_ID', '')}]: "
    ).strip() or values.get("META_APP_ID", "")
    if not re.fullmatch(r"[0-9]+", app_id):
        raise SystemExit("The app ID must contain digits only.")
    app_secret = getpass.getpass(
        "Meta app secret (hidden; Enter keeps the existing secret): "
    ).strip() or values.get("META_APP_SECRET", "")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", app_secret):
        raise SystemExit(
            "The Meta app secret should be 32 hexadecimal characters. Copy it from the Meta app dashboard."
        )
    config = input(
        "Facebook Login for Business configuration ID (optional; Enter keeps existing): "
    ).strip() or values.get("META_LOGIN_CONFIG_ID", "")
    if config and not config.isdigit():
        raise SystemExit("The configuration ID must contain digits only.")
    origin = values.get("APP_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise SystemExit("APP_ORIGIN must be the HTTPS studio origin, without a path.")
    key = (
        values.get("META_TOKEN_ENCRYPTION_KEY")
        or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    )
    try:
        if len(base64.urlsafe_b64decode(key)) != 32:
            raise ValueError("key")
    except (ValueError, TypeError):
        raise SystemExit(
            "The existing encryption key is invalid. Do not replace a key that protects connected accounts; restore it from backup."
        )
    updates = {
        "META_APP_ID": app_id,
        "META_APP_SECRET": app_secret,
        "META_LOGIN_CONFIG_ID": config,
        "META_TOKEN_ENCRYPTION_KEY": key,
        "META_GRAPH_VERSION": values.get("META_GRAPH_VERSION") or "v24.0",
        "META_PUBLISHING_ENABLED": "true",
    }
    if not re.fullmatch(r"v[0-9]{2}\.0", updates["META_GRAPH_VERSION"]):
        raise SystemExit("META_GRAPH_VERSION must look like v24.0.")
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.partition("=")[0].strip() not in updates
    ]
    lines += [
        "",
        "# Meta publishing: keep these values private and preserve the encryption key.",
    ] + [f"{k}={v}" for k, v in updates.items()]
    descriptor, temporary = tempfile.mkstemp(prefix=".env-meta-", dir=root)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Saved Meta app settings privately. No account tokens were displayed.")
    print(
        "Register this exact OAuth redirect in your Meta app: "
        + origin
        + "/publishing/connect"
    )
    print("Next: sudo ./scripts/install-service.sh")
    print("Then open GM Studio → Jobs → Publishing → Connect or reconnect Meta.")
    print(
        "The encryption key stays in .env and its encrypted backups; do not paste secrets into chat."
    )


if __name__ == "__main__":
    main()
