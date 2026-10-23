import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.edit_plan import EDIT_PLAN_JSON_SCHEMA, TalkingHeadEditPlan, deterministic_plan
from app.media_analysis import resolve_source


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
GATEWAY_RESPONSES_URL = "https://ai-gateway.vercel.sh/v1/responses"
REQUIRED_PLAN_SCOPE = "chatgpt.tokens.use.direct"


class ProviderUnavailable(RuntimeError):
    pass


class ProviderResponseError(RuntimeError):
    pass


def _read_json_response(response: Any, limit: int = 1_048_576) -> dict[str, Any]:
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ProviderResponseError("provider response exceeded the safety limit")
    decoded = json.loads(payload.decode("utf-8"))
    return decoded if isinstance(decoded, dict) else {}


def _safe_http_error(error: urllib.error.HTTPError) -> str:
    try:
        payload = error.read(65_537)
        if len(payload) > 65_536:
            return f"HTTP {error.code}"
        decoded = json.loads(payload.decode("utf-8"))
        if isinstance(decoded, dict):
            detail = decoded.get("detail")
            api_error = decoded.get("error")
            if isinstance(detail, str):
                return f"HTTP {error.code}: {detail[:500]}"
            if isinstance(api_error, dict):
                message = api_error.get("message") or api_error.get("code")
                if isinstance(message, str):
                    return f"HTTP {error.code}: {message[:500]}"
    except Exception:
        pass
    return f"HTTP {error.code}"


def _atomic_write_credentials(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_chatgpt_credentials(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProviderUnavailable(
            "ChatGPT plan usage is not connected. Follow the documented local enrollment and run scripts/import-chatgpt.sh."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("client_id", "access_token", "refresh_token", "expires_at", "scopes")
    if not isinstance(payload, dict) or any(key not in payload for key in required):
        raise ProviderUnavailable("the stored ChatGPT connection is incomplete; connect it again")
    scopes = payload.get("scopes")
    if not isinstance(scopes, list) or REQUIRED_PLAN_SCOPE not in scopes:
        raise ProviderUnavailable("the ChatGPT connection does not permit plan usage")
    return payload


def _refresh_chatgpt_credentials(path: Path, credentials: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": credentials["client_id"],
            "refresh_token": credentials["refresh_token"],
            "resource": "https://api.openai.com/v1",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_TOKEN_URL,
        data=body,
        headers={"content-type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            refreshed = _read_json_response(response)
    except urllib.error.HTTPError as error:
        raise ProviderUnavailable(f"ChatGPT connection refresh failed: {_safe_http_error(error)}") from error
    except OSError as error:
        raise ProviderUnavailable("ChatGPT connection refresh could not reach OpenAI") from error

    access_token = refreshed.get("access_token")
    refresh_token = refreshed.get("refresh_token")
    expires_in = refreshed.get("expires_in")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise ProviderUnavailable("ChatGPT connection refresh returned incomplete credentials")
    if not isinstance(expires_in, (int, float)):
        expires_in = 3600
    updated = {
        **credentials,
        **refreshed,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + float(expires_in),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    scopes = updated.get("scope")
    if isinstance(scopes, str):
        updated["scopes"] = sorted(set(scopes.split()))
    _atomic_write_credentials(path, updated)
    return updated


def usable_chatgpt_credentials(settings: Settings) -> dict[str, Any]:
    credentials = load_chatgpt_credentials(settings.chatgpt_credential_path)
    expires_at = float(credentials.get("expires_at") or 0)
    if expires_at <= time.time() + 120:
        credentials = _refresh_chatgpt_credentials(
            settings.chatgpt_credential_path,
            credentials,
            settings.editor_request_timeout_seconds,
        )
    return credentials


def _public_context(context: dict[str, Any], max_characters: int) -> dict[str, Any]:
    public = deepcopy(context)
    for asset in public.get("assets", []):
        for key in list(asset):
            if key.startswith("_"):
                del asset[key]
        simplified: list[dict[str, Any]] = []
        for segment in asset.get("transcript_segments", []):
            if not isinstance(segment, dict):
                continue
            simplified.append(
                {
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "text": segment.get("text"),
                }
            )
        asset["transcript_segments"] = simplified
    for track in public.get("music_library", []):
        for key in list(track):
            if key.startswith("_"):
                del track[key]

    encoded = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= max_characters:
        return public

    # Preserve inventory and timing facts while bounding long transcripts.
    originals: list[list[dict[str, Any]]] = []
    for asset in public.get("assets", []):
        originals.append(asset.get("transcript_segments", []))
        asset["transcript_segments"] = []
        asset["transcript_truncated"] = True
    base_size = len(json.dumps(public, ensure_ascii=False, separators=(",", ":")))
    remaining = max(0, max_characters - base_size)
    for asset, original_segments in zip(public.get("assets", []), originals, strict=True):
        retained: list[dict[str, Any]] = []
        for segment in original_segments:
            candidate = json.dumps(segment, ensure_ascii=False, separators=(",", ":"))
            if len(candidate) > remaining:
                break
            retained.append(segment)
            remaining -= len(candidate)
        asset["transcript_segments"] = retained
        asset["transcript_truncated"] = len(retained) < len(original_segments)
    return public


def _model_content(context: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    public = _public_context(context, settings.editor_max_context_characters)
    revision = public.get("revision")
    revision_instruction = ""
    if isinstance(revision, dict):
        revision_instruction = (
            "This is a revision of the supplied previous_plan. Follow the user's revision instruction "
            "while preserving requested strengths and all source-led constraints. Caption corrections "
            "are applied deterministically after planning; do not alter spoken words to simulate them.\n\n"
        )
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Create one JSON edit plan from this trusted job context. The validator will reject "
                "invented asset IDs, out-of-range timecodes, overlapping ranges, unsupported effects, "
                "and previews longer than 60 seconds. Prefer a coherent 15–60 second transcript-led "
                "story, preserve the speaker's meaning, remove obvious dead air, and keep chronological "
                "order unless the brief clearly requires otherwise. Treat job.target_duration_seconds "
                "as a real delivery target, job.must_include as required subject matter when supported "
                "by the transcript, and job.edit_style as the visual pacing direction. Use only the "
                "named visual and transition presets. For energetic edits, split around genuine emphasis "
                "beats, alternate standard framing with restrained punch-ins, and include a transition "
                "beat when the edit is at least 20 seconds. For clean edits, favor "
                "stable framing. For calm edits, favor longer clips and slow moves. Select music only from "
                "music_library and only when job.music_mode requests it; otherwise return no music.\n\n"
                + revision_instruction
                + json.dumps(public, ensure_ascii=False)
            ),
        }
    ]
    if context.get("project", {}).get("privacy_mode") != "hybrid":
        return content

    for asset in context.get("assets", [])[:4]:
        key = asset.get("_contact_sheet_key")
        if not isinstance(key, str):
            continue
        try:
            image_path = resolve_source(settings.media_root, key)
            if image_path.stat().st_size > 3_000_000:
                continue
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "input_text",
                    "text": f"Low-resolution contact sheet for asset {asset.get('asset_id')}:",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{encoded}",
                    "detail": "low",
                }
            )
        except (OSError, ValueError):
            continue
    return content


def _parse_sse_response(response: Any) -> str:
    chunks: list[str] = []
    completed = False
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        event_type = event.get("type")
        if event_type == "response.output_text.delta" and isinstance(event.get("delta"), str):
            chunks.append(event["delta"])
        elif event_type == "response.completed":
            completed = True
        elif event_type in {"response.failed", "response.incomplete", "error"}:
            error = event.get("error") or event.get("response", {}).get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            detail = str(code or message or event_type)
            if detail in {
                "subscription_sharing_usage_limit_exceeded",
                "subscription_sharing_usage_unavailable",
            }:
                raise ProviderUnavailable(f"ChatGPT plan usage is unavailable: {detail}")
            raise ProviderResponseError(f"editor model did not complete: {detail[:500]}")
    if not completed:
        raise ProviderResponseError("editor model stream ended without response.completed")
    output = "".join(chunks).strip()
    if not output:
        raise ProviderResponseError("editor model completed without an edit plan")
    return output


def _request_plan(
    *,
    endpoint: str,
    token: str,
    model: str,
    context: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    body = {
        "model": model,
        "instructions": (
            "You are GM Studio's bounded talking-head editor. Make editorial selections only from "
            "the supplied source inventory and transcript. Do not invent media, words, asset IDs, "
            "timecodes, paths, or operations outside the schema's named presets. Return only the "
            "required structured edit plan. "
            "Set post_copy to an empty string unless project.ai_copy_allowed is true. When it is true, "
            "post_copy may contain concise social caption text grounded only in the supplied transcript "
            "and brief; never invent factual claims."
        ),
        "input": [{"role": "user", "content": _model_content(context, settings)}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "talking_head_edit_plan",
                "description": "A source-led edit decision list for one vertical talking-head preview.",
                "strict": True,
                "schema": EDIT_PLAN_JSON_SCHEMA,
            }
        },
        "store": False,
        "stream": True,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.editor_request_timeout_seconds) as response:
            output = _parse_sse_response(response)
    except urllib.error.HTTPError as error:
        detail = _safe_http_error(error)
        if error.code in {401, 403, 429, 503}:
            raise ProviderUnavailable(detail) from error
        raise ProviderResponseError(detail) from error
    except TimeoutError as error:
        raise ProviderUnavailable("editor model request timed out") from error
    except OSError as error:
        raise ProviderUnavailable("editor model provider could not be reached") from error

    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise ProviderResponseError("editor model returned invalid JSON") from error
    if not isinstance(document, dict):
        raise ProviderResponseError("editor model returned a non-object edit plan")
    return document


def create_edit_plan(
    context: dict[str, Any], settings: Settings | None = None
) -> tuple[TalkingHeadEditPlan, dict[str, str]]:
    settings = settings or get_settings()
    privacy_mode = context.get("project", {}).get("privacy_mode")
    assets = context.get("assets", [])
    if privacy_mode == "local_only":
        revision = context.get("revision")
        if isinstance(revision, dict) and isinstance(revision.get("previous_plan"), dict):
            return TalkingHeadEditPlan.model_validate(revision["previous_plan"]), {
                "provider": "local_fixed_revision",
                "model": "talking_head_v1",
            }
        return deterministic_plan(
            assets,
            context.get("job", {}).get("target_duration_seconds"),
            context.get("job", {}).get("edit_style") or "clean",
            context.get("job", {}).get("music_mode") or "none",
            context.get("music_library", []),
        ), {
            "provider": "local_fixed_recipe",
            "model": "talking_head_v1",
        }

    primary_error: Exception | None = None
    try:
        credentials = usable_chatgpt_credentials(settings)
        document = _request_plan(
            endpoint=OPENAI_RESPONSES_URL,
            token=str(credentials["access_token"]),
            model=settings.chatgpt_model,
            context=context,
            settings=settings,
        )
        return TalkingHeadEditPlan.model_validate(document), {
            "provider": "chatgpt_plan",
            "model": settings.chatgpt_model,
        }
    except ProviderUnavailable as error:
        primary_error = error

    if settings.ai_gateway_fallback_enabled:
        if not settings.ai_gateway_api_key:
            raise ProviderUnavailable(
                "AI Gateway fallback is enabled but AI_GATEWAY_API_KEY is not set"
            ) from primary_error
        document = _request_plan(
            endpoint=GATEWAY_RESPONSES_URL,
            token=settings.ai_gateway_api_key,
            model=settings.ai_gateway_model,
            context=context,
            settings=settings,
        )
        return TalkingHeadEditPlan.model_validate(document), {
            "provider": "vercel_ai_gateway",
            "model": settings.ai_gateway_model,
        }

    assert primary_error is not None
    raise ProviderUnavailable(
        f"{primary_error} AI Gateway fallback is disabled, so no paid fallback was attempted."
    ) from primary_error
