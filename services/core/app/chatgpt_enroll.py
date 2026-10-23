import argparse
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt

from app.config import get_settings
from app.editor_provider import _atomic_write_credentials


ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _post_form(url: str, fields: dict[str, str], timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"content-type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI token exchange failed (HTTP {error.code}): {detail[:500]}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI token exchange returned an invalid response")
    return payload


def _validate_id_token(
    id_token: str, client_id: str, nonce: str | None = None
) -> dict[str, Any]:
    with urllib.request.urlopen(f"{ISSUER}/.well-known/openid-configuration", timeout=30) as response:
        configuration = json.load(response)
    jwks_uri = configuration.get("jwks_uri")
    if not isinstance(jwks_uri, str):
        raise RuntimeError("OpenAI identity configuration did not include a JWKS URI")
    header = jwt.get_unverified_header(id_token)
    algorithm = header.get("alg")
    if algorithm != "RS256":
        raise RuntimeError("OpenAI ID token did not use the expected RS256 signing algorithm")
    signing_key = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=ISSUER,
    )
    if nonce is not None and claims.get("nonce") != nonce:
        raise RuntimeError("OpenAI ID token nonce did not match this sign-in attempt")
    return claims


def import_credentials(import_path: Path) -> None:
    settings = get_settings()
    try:
        serialized = import_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError("the transferred ChatGPT credential could not be read") from error
    try:
        imported = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise RuntimeError("the transferred ChatGPT credential is not valid JSON") from error
    if not isinstance(imported, dict):
        raise RuntimeError("the transferred ChatGPT credential is not an object")

    required = ("client_id", "id_token", "access_token", "refresh_token", "scopes")
    if any(not imported.get(key) for key in required):
        raise RuntimeError("the transferred ChatGPT credential is incomplete")
    client_id = str(imported["client_id"])
    if not client_id.startswith("oaiapp_"):
        raise RuntimeError("the transferred credential does not have an issued client ID")
    scopes = imported.get("scopes")
    if not isinstance(scopes, list) or "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("the transferred credential does not permit ChatGPT plan usage")
    claims = _validate_id_token(str(imported["id_token"]), client_id)
    if imported.get("subject") not in {None, claims.get("sub")}:
        raise RuntimeError("the transferred credential identity did not match its ID token")

    existing: dict[str, Any] = {}
    if settings.chatgpt_credential_path.is_file():
        try:
            decoded = json.loads(settings.chatgpt_credential_path.read_text(encoding="utf-8"))
            existing = decoded if isinstance(decoded, dict) else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    if existing.get("subject") not in {None, claims.get("sub")}:
        raise RuntimeError("the transferred credential belongs to a different ChatGPT account")

    host_id = existing.get("ext_agent_host_id")
    if not isinstance(host_id, str):
        host_id = f"urn:uuid:{uuid4()}"
    record = {
        **imported,
        "email": claims.get("email"),
        "issuer": ISSUER,
        "subject": claims.get("sub"),
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "scopes": sorted(set(str(scope) for scope in scopes)),
        "imported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _atomic_write_credentials(settings.chatgpt_credential_path, record)
    print("GM Studio imported and validated ChatGPT plan credentials.", flush=True)
    print("The VM now owns token refreshes in its private Docker auth volume.", flush=True)


class CallbackState:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.query: dict[str, list[str]] | None = None


def _handler(state: CallbackState, expected_path: str) -> type[BaseHTTPRequestHandler]:
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != expected_path:
                self.send_error(404)
                return
            state.query = urllib.parse.parse_qs(parsed.query)
            state.event.set()
            body = (
                "<!doctype html><meta name='viewport' content='width=device-width'>"
                "<title>GM Studio connected</title>"
                "<body style='font-family:system-ui;padding:2rem;max-width:40rem'>"
                "<h1>Return to the terminal</h1>"
                "<p>GM Studio received the sign-in response. You can close this tab.</p></body>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return CallbackHandler


def enroll(host: str, port: int, timeout_seconds: int) -> None:
    settings = get_settings()
    credential_path = settings.chatgpt_credential_path
    existing: dict[str, Any] = {}
    if credential_path.is_file():
        try:
            decoded = json.loads(credential_path.read_text(encoding="utf-8"))
            existing = decoded if isinstance(decoded, dict) else {}
        except (OSError, json.JSONDecodeError):
            existing = {}

    host_id = existing.get("ext_agent_host_id")
    if not isinstance(host_id, str):
        host_id = f"urn:uuid:{uuid4()}"
    client_id = existing.get("client_id")
    returning = isinstance(client_id, str) and client_id.startswith("oaiapp_")
    authorization_client_id = client_id if returning else "dynamic_agent_client"

    state_value = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    callback_path = "/auth/callback"
    redirect_uri = f"http://127.0.0.1:{port}{callback_path}"
    parameters = {
        "client_id": authorization_client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state_value,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    if not returning:
        parameters["agent_name_hint"] = "GM Studio"
    elif isinstance(existing.get("email"), str):
        parameters["login_hint"] = existing["email"]

    callback = CallbackState()
    server = ThreadingHTTPServer((host, port), _handler(callback, callback_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print("Open this URL in the browser on the computer that owns the SSH tunnel:", flush=True)
        print(f"{AUTHORIZE_URL}?{urllib.parse.urlencode(parameters)}", flush=True)
        print("Waiting for the private loopback callback...", flush=True)
        if not callback.event.wait(timeout_seconds):
            raise RuntimeError("sign-in timed out before the callback arrived")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    query = callback.query or {}
    if query.get("state", [None])[0] != state_value:
        raise RuntimeError("sign-in state did not match this attempt")
    error = query.get("error", [None])[0]
    if error:
        raise RuntimeError(f"ChatGPT sign-in was not authorized: {error}")
    code = query.get("code", [None])[0]
    callback_client_id = query.get("client_id", [None])[0]
    issued_client_id = str(client_id) if returning else callback_client_id
    if not isinstance(code, str) or not code:
        raise RuntimeError("sign-in callback did not contain an authorization code")
    if not isinstance(issued_client_id, str) or not issued_client_id.startswith("oaiapp_"):
        raise RuntimeError("sign-in callback did not contain the issued client ID")
    if returning and callback_client_id not in {None, issued_client_id}:
        raise RuntimeError("sign-in callback returned a different client ID")

    tokens = _post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "client_id": issued_client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
        },
    )
    id_token = tokens.get("id_token")
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not all(isinstance(value, str) and value for value in (id_token, access_token, refresh_token)):
        raise RuntimeError("ChatGPT sign-in returned incomplete credentials")
    claims = _validate_id_token(str(id_token), issued_client_id, nonce)
    scopes = set(str(tokens.get("scope", "")).split())
    if "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("ChatGPT sign-in succeeded without permission to use the plan")
    if returning and existing.get("subject") not in {None, claims.get("sub")}:
        raise RuntimeError("the returning sign-in used a different ChatGPT account")

    expires_in = tokens.get("expires_in")
    if not isinstance(expires_in, (int, float)):
        expires_in = 3600
    record = {
        "email": claims.get("email"),
        "issuer": ISSUER,
        "subject": claims.get("sub"),
        "client_id": issued_client_id,
        "ext_agent_host_id": host_id,
        **tokens,
        "scopes": sorted(scopes),
        "expires_at": time.time() + float(expires_in),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _atomic_write_credentials(credential_path, record)
    print("GM Studio is connected to ChatGPT plan usage.", flush=True)
    print("The credential was saved inside the private Docker auth volume.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect GM Studio to ChatGPT plan usage")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=1455, type=int)
    parser.add_argument("--timeout", default=600, type=int)
    parser.add_argument("--import-credentials", type=Path)
    arguments = parser.parse_args()
    if arguments.import_credentials is not None:
        import_credentials(arguments.import_credentials)
        return
    enroll(arguments.host, arguments.port, arguments.timeout)


if __name__ == "__main__":
    main()
