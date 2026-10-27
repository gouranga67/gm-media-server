"""Small Meta transport. Never retries writes or exposes provider/token errors."""

import hashlib
import hmac
import http.client
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.fernet import Fernet, InvalidToken


class MetaError(RuntimeError):
    def __init__(self, message: str, *, ambiguous=False, reconnect=False):
        super().__init__(message)
        self.ambiguous = ambiguous
        self.reconnect = reconnect


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def identifier(value) -> str:
    result = str(value)
    if not re.fullmatch(r"[0-9]{1,80}", result):
        raise MetaError("Meta returned an invalid media or account identifier.")
    return result


def cipher(settings) -> Fernet:
    try:
        return Fernet(settings.meta_token_encryption_key.get_secret_value().encode())
    except (ValueError, TypeError) as error:
        raise MetaError(
            "Meta token encryption is not configured. Run the publishing setup script."
        ) from error


def encrypt_token(settings, token: str) -> str:
    return cipher(settings).encrypt(token.encode()).decode()


def decrypt_token(settings, value: str) -> str:
    try:
        return cipher(settings).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as error:
        raise MetaError(
            "The account connection cannot be opened. Reconnect it.", reconnect=True
        ) from error


def api(settings, path: str, *, token: str = "", method="GET", params=None) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9_/-]+", path):
        raise MetaError("Invalid Meta operation.")
    values = dict(params or {})
    if token:
        values["appsecret_proof"] = hmac.new(
            settings.meta_app_secret.get_secret_value().encode(),
            token.encode(),
            hashlib.sha256,
        ).hexdigest()
    data = urlencode(values).encode()
    url = f"https://graph.facebook.com/{settings.meta_graph_version}/{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method == "GET":
        url += "?" + data.decode()
        data = None
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with build_opener(NoRedirect()).open(
            Request(url, data=data, headers=headers, method=method), timeout=30
        ) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("response too large")
            result = json.loads(raw)
    except HTTPError as error:
        try:
            provider = json.loads(error.read(65536)).get("error", {})
            code = int(provider.get("code", 0))
        except (ValueError, TypeError, AttributeError):
            code = 0
        message = (
            "Meta access expired or was revoked. Reconnect the account."
            if code == 190
            else "Meta publishing permission is missing. Check the connected Page and app permissions."
            if code in {10, 200}
            else "Meta rejected this operation. Check account eligibility, permissions and video requirements."
        )
        raise MetaError(
            message,
            ambiguous=error.code >= 500 and method != "GET",
            reconnect=code == 190,
        ) from None
    except (URLError, OSError, ValueError, http.client.HTTPException):
        raise MetaError(
            "Meta did not return a verifiable response.", ambiguous=method != "GET"
        ) from None
    if not isinstance(result, dict) or result.get("error"):
        raise MetaError(
            "Meta returned an unexpected response.", ambiguous=method != "GET"
        )
    return result


def validate_upload_uri(uri: str) -> tuple[str, str]:
    url = urlsplit(uri)
    if (
        url.scheme != "https"
        or url.hostname != "rupload.facebook.com"
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.fragment
    ):
        raise MetaError("Meta returned an untrusted upload destination.")
    if not url.path.startswith(("/ig-api-upload/", "/video-upload/")):
        raise MetaError("Meta returned an unexpected upload path.")
    return url.hostname, url.path + ("?" + url.query if url.query else "")


def upload_file(uri: str, source: Path, token: str) -> None:
    host, target = validate_upload_uri(uri)
    size = source.stat().st_size
    channel = http.client.HTTPSConnection(host, timeout=60)
    deadline = time.monotonic() + 900
    try:
        channel.putrequest("POST", target)
        for key, value in {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(size),
            "Content-Length": str(size),
            "Content-Type": "application/octet-stream",
        }.items():
            channel.putheader(key, value)
        channel.endheaders()
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                if time.monotonic() >= deadline:
                    raise OSError("upload deadline reached")
                channel.send(chunk)
        response = channel.getresponse()
        result = json.loads(response.read(65536))
        if response.status // 100 != 2 or not result.get("success"):
            raise MetaError(
                "Meta did not confirm the video upload. Check status before trying again.",
                ambiguous=True,
            )
    except (OSError, ValueError, http.client.HTTPException):
        raise MetaError(
            "The video upload response is uncertain. Check status before trying again.",
            ambiguous=True,
        ) from None
    finally:
        channel.close()


def begin_upload(settings, post: dict, token: str) -> tuple[str, str]:
    external = identifier(post["external_id"])
    if post["platform"] == "instagram":
        result = api(
            settings,
            external + "/media",
            token=token,
            method="POST",
            params={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": post["caption"],
                "share_to_feed": "true",
                "thumb_offset": str(
                    round(float(post.get("cover_time_seconds") or 0) * 1000)
                ),
            },
        )
        container, uri = identifier(result.get("id")), result.get("uri")
    else:
        result = api(
            settings,
            external + "/video_reels",
            token=token,
            method="POST",
            params={"upload_phase": "start"},
        )
        container, uri = identifier(result.get("video_id")), result.get("upload_url")
    validate_upload_uri(str(uri))
    return container, str(uri)


def processing_status(settings, post: dict, token: str) -> str:
    container = identifier(post["remote_container_id"])
    result = api(
        settings,
        container,
        token=token,
        params={
            "fields": "status_code" if post["platform"] == "instagram" else "status"
        },
    )
    if post["platform"] == "instagram":
        state = result.get("status_code")
        return {
            "FINISHED": "ready",
            "PUBLISHED": "published",
            "ERROR": "failed",
            "EXPIRED": "failed",
        }.get(state, "processing")
    state = result.get("status") or {}
    publishing = (state.get("publishing_phase") or {}).get("status")
    if publishing == "complete":
        return "published"
    if state.get("video_status") == "error" or any(
        (state.get(phase) or {}).get("status") == "error"
        for phase in ("uploading_phase", "processing_phase", "publishing_phase")
    ):
        return "failed"
    if (state.get("processing_phase") or {}).get("status") == "complete" or state.get(
        "video_status"
    ) == "ready":
        return "ready"
    return "processing"


def publish(settings, post: dict, token: str) -> str:
    external, container = (
        identifier(post["external_id"]),
        identifier(post["remote_container_id"]),
    )
    if post["platform"] == "instagram":
        result = api(
            settings,
            external + "/media_publish",
            token=token,
            method="POST",
            params={"creation_id": container},
        )
        try:
            return identifier(result.get("id"))
        except MetaError:
            raise MetaError(
                "Meta did not return a verifiable published media ID. Check remote status before retrying.",
                ambiguous=True,
            ) from None
    result = api(
        settings,
        external + "/video_reels",
        token=token,
        method="POST",
        params={
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "video_id": container,
            "description": post["caption"],
        },
    )
    if result.get("success") is not True:
        raise MetaError(
            "Meta did not confirm publication. Check status before retrying.",
            ambiguous=True,
        )
    return container


def permalink(settings, post: dict, token: str) -> str | None:
    if not post.get("remote_media_id"):
        return None
    result = api(
        settings,
        identifier(post["remote_media_id"]),
        token=token,
        params={
            "fields": "permalink"
            if post["platform"] == "instagram"
            else "permalink_url"
        },
    )
    value = result.get("permalink") or result.get("permalink_url")
    url = urlsplit(value or "")
    if (
        url.scheme == "https"
        and url.hostname
        in {"www.instagram.com", "instagram.com", "www.facebook.com", "facebook.com"}
        and not url.username
        and not url.password
    ):
        return value
    return None
