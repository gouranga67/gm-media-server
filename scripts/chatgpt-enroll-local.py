#!/usr/bin/env python3
"""Run on the browser computer, then securely transfer the output to the VM."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import jwt
except ImportError as error:
    raise SystemExit(
        'Install the helper dependency first: py -m pip install "PyJWT[crypto]==2.10.1"'
    ) from error


ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"content-type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenAI token exchange failed (HTTP {error.code}): {detail[:500]}"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI token exchange returned an invalid response")
    return payload


def validate_id_token(id_token: str, client_id: str, nonce: str) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"{ISSUER}/.well-known/openid-configuration", timeout=30
    ) as response:
        configuration = json.load(response)
    jwks_uri = configuration.get("jwks_uri")
    if not isinstance(jwks_uri, str):
        raise RuntimeError("OpenAI identity configuration did not include a JWKS URI")
    header = jwt.get_unverified_header(id_token)
    if header.get("alg") != "RS256":
        raise RuntimeError("OpenAI ID token did not use RS256")
    key = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=ISSUER,
    )
    if claims.get("nonce") != nonce:
        raise RuntimeError("OpenAI ID token nonce did not match this sign-in attempt")
    return claims


class CallbackState:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.query: dict[str, list[str]] | None = None


def callback_handler(state: CallbackState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_error(404)
                return
            state.query = urllib.parse.parse_qs(parsed.query)
            state.event.set()
            body = (
                "<!doctype html><meta name='viewport' content='width=device-width'>"
                "<title>GM Studio connected</title>"
                "<body style='font-family:system-ui;padding:2rem'>"
                "<h1>Return to the terminal</h1><p>You can close this tab.</p></body>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    temporary = path.with_name(f".{path.name}.part")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def enroll(output_path: Path, port: int, timeout: int) -> None:
    state_value = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    local_host_id = f"urn:uuid:{uuid4()}"
    redirect_uri = f"http://127.0.0.1:{port}/auth/callback"
    parameters = {
        "client_id": "dynamic_agent_client",
        "agent_name_hint": "GM Studio",
        "ext_agent_host_id": local_host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state_value,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    callback = CallbackState()
    server = ThreadingHTTPServer(("127.0.0.1", port), callback_handler(callback))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authorization_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(parameters)}"
    print("Opening ChatGPT authorization in your browser...", flush=True)
    if not webbrowser.open(authorization_url):
        print(authorization_url, flush=True)
    try:
        if not callback.event.wait(timeout):
            raise RuntimeError("sign-in timed out before the callback arrived")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    query = callback.query or {}
    if query.get("state", [None])[0] != state_value:
        raise RuntimeError("sign-in state did not match this attempt")
    if query.get("error", [None])[0]:
        raise RuntimeError(f"ChatGPT sign-in was not authorized: {query['error'][0]}")
    code = query.get("code", [None])[0]
    client_id = query.get("client_id", [None])[0]
    if not isinstance(code, str) or not code:
        raise RuntimeError("sign-in callback did not contain an authorization code")
    if not isinstance(client_id, str) or not client_id.startswith("oaiapp_"):
        raise RuntimeError("sign-in callback did not contain the issued client ID")
    tokens = post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
        },
    )
    required = ("id_token", "access_token", "refresh_token")
    if any(not isinstance(tokens.get(key), str) or not tokens[key] for key in required):
        raise RuntimeError("ChatGPT sign-in returned incomplete credentials")
    claims = validate_id_token(str(tokens["id_token"]), client_id, nonce)
    scopes = sorted(set(str(tokens.get("scope", "")).split()))
    if "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("ChatGPT sign-in did not grant plan usage")
    expires_in = tokens.get("expires_in")
    if not isinstance(expires_in, (int, float)):
        expires_in = 3600
    record = {
        "email": claims.get("email"),
        "issuer": ISSUER,
        "subject": claims.get("sub"),
        "client_id": client_id,
        "ext_agent_host_id": local_host_id,
        **tokens,
        "scopes": scopes,
        "expires_at": time.time() + float(expires_in),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    atomic_write(output_path, record)
    print(f"Saved protected transfer file: {output_path.resolve()}", flush=True)
    print("Copy it to the server now; do not email it or open it in an editor.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a GM Studio ChatGPT credential locally")
    parser.add_argument("--output", type=Path, default=Path("gm-studio-chatgpt.json"))
    parser.add_argument("--port", type=int, default=1455)
    parser.add_argument("--timeout", type=int, default=600)
    arguments = parser.parse_args()
    enroll(arguments.output, arguments.port, arguments.timeout)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"ChatGPT enrollment failed: {error}") from error
