"""Bounded Google Drive OAuth and download transport for explicit user selections."""

import json
import re
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
FILE_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


class GoogleDriveError(RuntimeError):
    def __init__(self, message: str, *, reconnect: bool = False, retryable: bool = False):
        super().__init__(message)
        self.reconnect = reconnect
        self.retryable = retryable


def configured(settings) -> bool:
    return bool(
        settings.google_drive_enabled
        and settings.google_drive_client_id
        and settings.google_drive_client_secret.get_secret_value()
        and settings.google_drive_token_encryption_key.get_secret_value()
        and settings.google_drive_api_key.get_secret_value()
        and settings.google_drive_app_id
        and settings.google_drive_app_origin
    )


def redirect_uri(settings) -> str:
    return settings.google_drive_app_origin.rstrip("/") + "/api/media/google-drive/callback"


def authorization_url(settings, state: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": settings.google_drive_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": DRIVE_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    })


def _cipher(settings) -> Fernet:
    try:
        return Fernet(settings.google_drive_token_encryption_key.get_secret_value().encode())
    except (TypeError, ValueError) as error:
        raise GoogleDriveError("Google Drive token encryption is not configured.") from error


def encrypt_refresh_token(settings, value: str) -> str:
    return _cipher(settings).encrypt(value.encode()).decode()


def decrypt_refresh_token(settings, value: str) -> str:
    try:
        return _cipher(settings).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as error:
        raise GoogleDriveError(
            "The Google Drive connection cannot be opened. Reconnect it.", reconnect=True
        ) from error


def _token_request(settings, values: dict[str, str]) -> dict:
    request = Request(
        TOKEN_URL,
        data=urlencode(values).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(128_001)
            if len(raw) > 128_000:
                raise ValueError("response too large")
            result = json.loads(raw)
    except HTTPError as error:
        reconnect = error.code in {400, 401}
        raise GoogleDriveError(
            "Google Drive authorization expired. Reconnect it." if reconnect
            else "Google Drive authorization is temporarily unavailable.",
            reconnect=reconnect,
            retryable=error.code >= 500,
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        raise GoogleDriveError(
            "Google Drive authorization is temporarily unavailable.", retryable=True
        ) from error
    if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
        raise GoogleDriveError("Google Drive returned an incomplete authorization response.")
    return result


def exchange_code(settings, code: str) -> dict:
    return _token_request(settings, {
        "client_id": settings.google_drive_client_id,
        "client_secret": settings.google_drive_client_secret.get_secret_value(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(settings),
    })


def refresh_access_token(settings, refresh_token: str) -> str:
    result = _token_request(settings, {
        "client_id": settings.google_drive_client_id,
        "client_secret": settings.google_drive_client_secret.get_secret_value(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    return str(result["access_token"])


def _validated_file_id(file_id: str) -> str:
    if not FILE_ID.fullmatch(file_id):
        raise GoogleDriveError("Google Drive returned an invalid file selection.")
    return file_id


def file_metadata(access_token: str, file_id: str) -> dict:
    identifier = _validated_file_id(file_id)
    fields = "id,name,mimeType,size,md5Checksum,modifiedTime,trashed,capabilities(canDownload)"
    url = f"https://www.googleapis.com/drive/v3/files/{quote(identifier)}?" + urlencode({
        "fields": fields,
        "supportsAllDrives": "true",
    })
    request = Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(256_001)
            if len(raw) > 256_000:
                raise ValueError("response too large")
            result = json.loads(raw)
    except HTTPError as error:
        reconnect = error.code == 401
        raise GoogleDriveError(
            "Google Drive access expired. Reconnect it." if reconnect
            else "That Drive file is unavailable or no longer shared with GM Studio.",
            reconnect=reconnect,
            retryable=error.code in {408, 429} or error.code >= 500,
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        raise GoogleDriveError("Google Drive is temporarily unavailable.", retryable=True) from error
    if not isinstance(result, dict) or result.get("id") != identifier:
        raise GoogleDriveError("Google Drive returned invalid file information.")
    return result


def download_file(
    access_token: str,
    file_id: str,
    destination: Path,
    expected_size: int,
    progress: Callable[[int], None] | None = None,
) -> None:
    """Resume a selected blob download into a staging file."""
    identifier = _validated_file_id(file_id)
    if expected_size <= 0:
        raise GoogleDriveError("The selected Drive file has no downloadable content.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = destination.stat().st_size if destination.is_file() else 0
    if existing > expected_size:
        destination.unlink()
        existing = 0
    if existing == expected_size:
        if progress:
            progress(existing)
        return
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/octet-stream"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    url = f"https://www.googleapis.com/drive/v3/files/{quote(identifier)}?alt=media&supportsAllDrives=true"
    try:
        with urlopen(Request(url, headers=headers), timeout=120) as response:
            partial = response.status == 206
            mode = "ab" if existing and partial else "wb"
            downloaded = existing if mode == "ab" else 0
            with destination.open(mode) as output:
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > expected_size:
                        raise GoogleDriveError("Google Drive sent more data than expected.")
                    if progress:
                        progress(downloaded)
    except HTTPError as error:
        reconnect = error.code == 401
        raise GoogleDriveError(
            "Google Drive access expired. Reconnect it." if reconnect
            else "The Drive download was interrupted and will retry.",
            reconnect=reconnect,
            retryable=error.code in {408, 429} or error.code >= 500,
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise GoogleDriveError("The Drive download was interrupted and will retry.", retryable=True) from error
    final_size = destination.stat().st_size if destination.is_file() else 0
    if final_size != expected_size:
        raise GoogleDriveError("The Drive download was incomplete and will retry.", retryable=True)
