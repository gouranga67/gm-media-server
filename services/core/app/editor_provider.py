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
from app.edit_plan import (
    EditPlan,
    MontageEditPlan,
    TalkingHeadEditPlan,
    deterministic_montage_plan,
    deterministic_plan,
    schema_for_recipe,
)
from app.media_analysis import resolve_source


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
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


def list_chatgpt_models(settings: Settings | None = None) -> list[dict[str, str]]:
    settings = settings or get_settings()
    credentials = usable_chatgpt_credentials(settings)
    request = urllib.request.Request(
        OPENAI_MODELS_URL,
        headers={"authorization": f"Bearer {credentials['access_token']}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.editor_request_timeout_seconds) as response:
            payload = _read_json_response(response)
    except urllib.error.HTTPError as error:
        raise ProviderUnavailable(f"ChatGPT model catalogue failed: {_safe_http_error(error)}") from error
    except OSError as error:
        raise ProviderUnavailable("ChatGPT model catalogue could not reach OpenAI") from error
    models = payload.get("models")
    if not isinstance(models, list):
        raise ProviderResponseError("ChatGPT model catalogue returned an unexpected response")
    visible: list[dict[str, str]] = []
    for model in models:
        if not isinstance(model, dict) or model.get("visibility") != "list":
            continue
        slug = model.get("slug")
        display_name = model.get("display_name")
        if (
            not isinstance(slug, str)
            or not isinstance(display_name, str)
            or not display_name.strip()
        ):
            continue
        if not slug or len(slug) > 160 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
            for character in slug
        ):
            continue
        visible.append({"slug": slug, "display_name": display_name.strip()[:160]})
    if not visible:
        raise ProviderResponseError("ChatGPT model catalogue did not include selectable models")
    return visible


def _public_context(context: dict[str, Any], max_characters: int) -> dict[str, Any]:
    public = deepcopy(context)
    for asset in public.get("assets", []):
        for key in list(asset):
            if key.startswith("_") or key in {"sha256", "byte_size", "asset_status", "analysis_status"}:
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
        story_index = asset.get("story_index")
        if isinstance(story_index, dict):
            moments = story_index.get("moments")
            if isinstance(moments, list):
                story_index["moments"] = moments[:24]
                for moment in story_index["moments"]:
                    if not isinstance(moment, dict):
                        continue
                    # Parent identity and duplicate scores do not add editorial
                    # evidence. Keep every card, utterance, role, and cut hint.
                    for key in ("asset_id", "source_name"):
                        if moment.get(key) == asset.get(key):
                            moment.pop(key, None)
                    roles = moment.get("role_scores")
                    components = moment.get("score_components")
                    if isinstance(roles, dict) and isinstance(components, dict):
                        moment["score_components"] = {
                            key: value for key, value in components.items()
                            if key not in roles or roles[key] != value
                        }

    # Rights are enforced against the full server-side inventory and retained
    # in delivery credits. The planner needs creative descriptors, not repeated
    # license URLs, platform lists, attribution paragraphs, or storage paths.
    for library_name in ("music_library", "creative_effect_library"):
        for item in public.get(library_name, []):
            for key in list(item):
                if key.startswith("_") or key in {
                    "license_source_url", "license_proof_recorded", "allowed_platforms", "attribution",
                }:
                    del item[key]
    direction = public.get("job") or {}
    if direction.get("music_mode") == "none":
        public["music_library"] = []
    elif direction.get("selected_music_track_id"):
        selected = [track for track in public.get("music_library", [])
                    if str(track.get("track_id")) == str(direction["selected_music_track_id"])]
        if selected:
            public["music_library"] = selected
    if direction.get("effect_level") == "off":
        public["creative_effect_library"] = []

    encoded = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= max_characters:
        return public

    # Reduce duplicate highlight evidence before allocating transcript space.
    for asset in public.get("assets", []):
        story_index = asset.get("story_index")
        if isinstance(story_index, dict) and isinstance(story_index.get("moments"), list):
            moments = story_index["moments"]
            story_index["moments"] = moments[:8]
            story_index["moments_truncated"] = len(moments) > 8
    if len(json.dumps(public, ensure_ascii=False, separators=(",", ":"))) <= max_characters:
        return public

    # Share the remaining budget across sources and across each source's
    # beginning, middle and ending. Never silently retain only the first file.
    originals = []
    for asset in public.get("assets", []):
        originals.append(asset.get("transcript_segments", []))
        asset["transcript_segments"] = []
        asset["transcript_truncated"] = True
        asset["transcript_segment_count"] = len(originals[-1])
    public["transcript_coverage"] = "sampled_across_sources_and_time"
    base_size = len(json.dumps(public, ensure_ascii=False, separators=(",", ":")))
    remaining = max_characters - base_size
    if remaining < 0:
        raise ProviderResponseError("editor inventory exceeds the context limit; use fewer sources")
    queues = []
    for segments in originals:
        # Endpoints first, then recursively fill the largest temporal gaps.
        pending = [(0, len(segments) - 1)] if segments else []
        order = []
        if segments:
            order = [0] if len(segments) == 1 else [0, len(segments) - 1]
        while pending:
            left, right = pending.pop(0)
            if right - left > 1:
                middle = (left + right) // 2
                order.append(middle)
                pending.extend([(left, middle), (middle, right)])
        queues.append(order)
    retained = [set() for _ in originals]
    while any(queues):
        for index, queue in enumerate(queues):
            if not queue:
                continue
            segment_index = queue.pop(0)
            segment = originals[index][segment_index]
            cost = len(json.dumps(segment, ensure_ascii=False, separators=(",", ":"))) + 1
            if cost <= remaining:
                retained[index].add(segment_index)
                remaining -= cost
    for asset, segments, indexes in zip(public.get("assets", []), originals, retained):
        asset["transcript_segments"] = [segments[index] for index in sorted(indexes)]
        asset["transcript_truncated"] = len(indexes) < len(segments)
    return public


def _model_content(context: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    public = _public_context(context, settings.editor_max_context_characters)
    revision = public.get("revision")
    revision_instruction = ""
    if isinstance(revision, dict):
        locked = revision.get("locked_elements") or []
        locked_instruction = (
            " The user locked these elements; preserve them exactly unless the revision explicitly asks to unlock one: "
            + ", ".join(str(item) for item in locked)
            + "."
            if locked else ""
        )
        scope_instruction = (
            "Rebuild the story from all available source transcripts and the original brief. "
            "The previous plan is a rejected draft, not a template: you may replace, reorder, "
            "and retime unlocked clips. Identify the supported beginning, development, and payoff "
            "before selecting cuts. Keep causal connections, complete thoughts, and necessary setup. "
            if revision.get("mode") == "rebuild_story" else
            "Make the requested changes to the previous plan while preserving unrelated strengths. "
        )
        revision_instruction = (
            "This is a revision. The current instruction is: "
            + str(revision.get("instruction") or "")
            + "\n" + scope_instruction
            + "Use source passages outside the previous cut when needed. A response that merely "
              "rewrites editorial_summary without changing the requested edit is insufficient. "
              "In editorial_summary, explain the concrete changes and any request the available "
              "footage cannot satisfy. Caption corrections are applied deterministically after planning; "
              "do not alter spoken words to simulate them."
            + locked_instruction + "\n\n"
        )
    learning = public.get("learning_preferences")
    learning_directives = learning.get("directives") if isinstance(learning, dict) else []
    learning_instruction = ""
    if isinstance(learning_directives, list) and learning_directives:
        learning_instruction = (
            "These preferences were learned locally from repeated explicit user feedback for this recipe. "
            "Apply them when compatible with the current brief and source evidence; never invent material or "
            "override an explicit job instruction: "
            + " ".join(str(item) for item in learning_directives[:8])
            + "\n\n"
        )
    correction = public.get("validation_correction")
    correction_instruction = ""
    if isinstance(correction, dict):
        correction_instruction = (
            "Your previous edit plan was rejected by the deterministic validator. Correct the supplied "
            "rejected_plan so it satisfies every original instruction and this exact validation error: "
            f"{str(correction.get('error') or 'invalid edit plan')[:1000]}. Return a complete replacement "
            "plan, not a patch. Do not repeat overlapping source ranges from the same video asset.\n\n"
        )
    recipe = str(public.get("job", {}).get("recipe") or "talking_head")
    take_instruction = (
        "Story quality takes precedence over humour, music, and effects. A funny tone or meme_heavy "
        "effect level is not a request for a blooper reel. Read every source's take_quality report and "
        "compare repeated takes before selecting footage. Prefer a complete clean take over false starts, "
        "readiness checks, retake directions, and discussions about changing the script. These local flags "
        "are evidence to verify against the full transcript, not certainty about the speaker's intent. "
        "For a promotional video, identify the actual product or subject, give the supported benefit or "
        "demonstration and proof, and finish the thought. Do not omit the product introduction just to "
        "make room for a joke. If humour fits, use a short reaction after the main point; never make "
        "an entire failed take the development/payoff unless the brief explicitly requests outtakes. "
        "Do not confuse source order with story order: compare takes across all sources and use the "
        "cleanest complete version, preserving cause and effect. Source speech gaps are not verified "
        "silence; keep only a brief supported reaction and trim unused stretches. New promotional "
        "dialogue cuts receive local pause tightening by default; explicit instructions to preserve "
        "pauses or make a blooper reel take precedence.\n\n"
    )
    if recipe == "montage":
        task_instruction = (
            "Create one source-led montage JSON edit plan. Choose only uploaded video and image assets. "
            "Build a deliberate story spine from job.story direction and the locally retrieved story_index "
            "moments. Treat story_spine.engagement_assessment as trusted local editorial guidance: compare its "
            "hook alternatives, cover its missing roles where source evidence allows, avoid its duplicate-idea "
            "groups, and prefer clean cut points. Open with the strongest supported hook, orient the viewer, build with new information, "
            "place the best supported moment near the payoff, and finish cleanly. Assign every clip a story_role "
            "and a short editorial_intent that explains its contribution. Prefer sharp, varied shots and coherent "
            "visual progression grounded in the brief. Do not claim that a generic visual_window depicts an object "
            "unless the supplied contact sheet supports that conclusion. Video clip "
            "duration must exactly match source_out minus source_in; image clips use zero source timecodes. "
            "Use 1.5–4 second shots for energetic work and 3–6 second shots for calm work. Keep every clip "
            "between 0.5 and 8 seconds. The requested duration is an approximate aim, never a minimum; "
            "end sooner when the story is complete and never pad with dead air or duplicate material. "
            "Use speech_gaps to avoid unintended hesitations in dialogue while preserving supported "
            "laughter and reaction beats. Use only named "
            "presets, and select music only from music_library when requested. If the brief names dialogue or "
            "a spoken phrase, include the whole supported utterance and enable source audio for that clip; do "
            "not begin or end in the middle of a word. Set source_audio_gain_db to 0 for ordinary source sound. "
            "When the user explicitly asks to make a named speaker, phrase, or moment louder, keep source audio "
            "enabled and use +6 to +12 dB on that exact clip; use negative gain only when the user asks to lower "
            "it. Muted clips and image clips must use 0 dB. Use source audio sparingly for complete dialogue beats "
            "or useful natural sound, never as arbitrary fragments. The renderer automatically ducks selected "
            "music beneath audible source clips. When no music is requested, favor a few "
            "coherent audio passages over rapid on/off audio switching. When a selected track has a beat grid, "
            "prefer cumulative cut times near those beats. Use creative_effect_library only when "
            "job.effect_level is enabled. Every effect must support a real hook, transition, emphasis, reveal, "
            "reaction, or payoff; match the asset's reviewed purpose, keep cues within the finished timeline, "
            "and prefer restraint over decoration. Subtle permits at most 2 cues, social 4, and meme_heavy 8."
        )
    else:
        task_instruction = (
            "Create one JSON edit plan from this trusted job context. The validator will reject invented "
            "asset IDs, out-of-range timecodes, overlapping ranges, unsupported effects, and previews longer "
            "than 60 seconds. Use story_spine and the locally retrieved story_index moments to build a coherent "
            "short transcript-led story. Read the supplied transcript in source order; moment cards "
            "are retrieval hints. Preserve connecting dialogue, cause and effect, pronoun references, "
            "necessary setup, and the speaker's conclusion. Use story_spine.engagement_assessment to compare hook/payoff/ending "
            "candidates, avoid repeated-idea groups, and prefer complete thoughts with clean edit points. Start with "
            "the strongest supported hook instead of routine setup, "
            "then give only the context needed to understand the point, develop it, deliver a payoff, and follow "
            "the requested ending. Assign every clip a story_role and a concise editorial_intent. Preserve the speaker's "
            "meaning, remove obvious dead air, and keep chronological order unless the brief clearly requires "
            "otherwise. Treat job.target_duration_seconds as an approximate aim, never a minimum. "
            "A shorter complete story is better than dead air, repeated information, or a blooper added "
            "to fill time. Use the explicit speech_gaps to cut excessive hesitation; a typical retained "
            "pause is 0.3–0.6s and a short comedy beat about 0.8s. Speech gaps can contain laughter or "
            "meaningful visual reactions: preserve those when supported by the brief or source evidence. "
            "Treat job.must_include as "
            "required subject matter when supported by the transcript, and job.edit_style as the visual pacing "
            "direction. Use only the named visual and transition presets. For energetic edits, split around "
            "genuine emphasis beats identified in the source evidence, alternate standard framing with restrained "
            "punch-ins, keep complete phrases intact, and include a "
            "transition beat when the edit is at least 20 seconds. For clean edits, favor stable framing. For "
            "calm edits, favor longer clips and slow moves. Select music only from music_library and only when "
            "job.music_mode requests it; otherwise return no music. Use creative_effect_library only when "
            "job.effect_level is enabled. Every effect must support a real hook, transition, emphasis, reveal, "
            "reaction, or payoff; match the asset's reviewed purpose, keep cues within the finished timeline, "
            "and prefer restraint over decoration. Subtle permits at most 2 cues, social 4, and meme_heavy 8."
        )
    finishing_instruction = (
        "High impact finishing: assemble a coherent dialogue story first. Then aim for a purposeful picture or "
        "sound change about every 2–3 seconds, allowing important lines and reactions to breathe. "
        "For long talking shots, rhythmic_punch alternates standard and 12% punch-in framing every 2.5s "
        "without cutting the audio. Mix that with ordinary cuts, static emphasis, and suitable sound accents; "
        "Keep reaction holds and intentional breathing room steady; mark such a shot with hold, steady, or breathe in editorial_intent. "
        "do not put a sound on every beat. When effects are enabled, select reviewed clicks/dings/pops for real "
        "reveals or emphasis, whooshes for movement, and comedic sounds only for earned reactions. Respect cue limits. "
        "Use broll for 0.5–4s picture-only cutaways to relevant uploaded video or image assets. Main speech continues "
        "unchanged under broll; never replace dialogue clips just to show a product close-up. Give each overlay a "
        "source-backed editorial_intent. Do not infer an object from a generic visual_window or invent relevant footage. "
        "Overlays must not overlap, must stay inside the final edit, and may cover at most 60% of it. "
        "Image overlays use zero source timecodes; video duration must equal source_out-source_in. Return [] if no "
        "appropriate B-roll is supplied.\n\n"
        if public.get("job", {}).get("edit_style") == "high_impact"
        else "Return broll as []; picture overlays are enabled only by the High impact style.\n\n"
    )
    if public.get("job", {}).get("broll_enabled") is False:
        finishing_instruction += "The user removed B-roll. Return broll as [] and preserve the main speech.\n\n"
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                task_instruction
                + "\n\n"
                + take_instruction
                + learning_instruction
                + revision_instruction
                + correction_instruction
                + finishing_instruction
                + json.dumps(public, ensure_ascii=False, separators=(",", ":"))
            ),
        }
    ]
    if context.get("project", {}).get("privacy_mode") != "hybrid":
        return content

    image_limit = 12 if recipe == "montage" else 4
    for asset in context.get("assets", [])[:image_limit]:
        key = asset.get("_contact_sheet_key") or asset.get("_preview_key")
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


def _parse_sse_response(response: Any) -> tuple[str, dict[str, Any]]:
    chunks: list[str] = []
    completed = False
    completion: dict[str, Any] = {}
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
            response_payload = event.get("response")
            if isinstance(response_payload, dict):
                completion = response_payload
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
    usage = completion.get("usage") if isinstance(completion.get("usage"), dict) else {}
    input_details = (
        usage.get("input_tokens_details")
        if isinstance(usage.get("input_tokens_details"), dict)
        else {}
    )
    output_details = (
        usage.get("output_tokens_details")
        if isinstance(usage.get("output_tokens_details"), dict)
        else {}
    )
    return output, {
        "response_id": completion.get("id") if isinstance(completion.get("id"), str) else None,
        "actual_model": completion.get("model") if isinstance(completion.get("model"), str) else None,
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_input_tokens": int(input_details.get("cached_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_tokens": int(output_details.get("reasoning_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _request_plan(
    *,
    endpoint: str,
    token: str,
    model: str,
    reasoning_effort: str,
    context: dict[str, Any],
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    recipe = str(context.get("job", {}).get("recipe") or "talking_head")
    schema = schema_for_recipe(recipe)
    body = {
        "model": model,
        "instructions": (
            "You are GM Studio's bounded source-led video editor. Make editorial selections only from "
            "the supplied source inventory, analysis, and transcript. Do not invent media, words, asset IDs, "
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
                "name": f"{recipe}_edit_plan",
                "description": f"A source-led edit decision list for one {recipe} preview.",
                "strict": True,
                "schema": schema,
            }
        },
        "reasoning": {"effort": reasoning_effort},
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
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=settings.editor_request_timeout_seconds) as response:
            output, usage = _parse_sse_response(response)
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
    usage["latency_ms"] = max(0, round((time.monotonic() - started) * 1000))
    return document, usage


def create_edit_plan(
    context: dict[str, Any], settings: Settings | None = None
) -> tuple[EditPlan, dict[str, Any]]:
    settings = settings or get_settings()
    privacy_mode = context.get("project", {}).get("privacy_mode")
    assets = context.get("assets", [])
    recipe = str(context.get("job", {}).get("recipe") or "talking_head")
    selected_model = str(context.get("job", {}).get("editor_model") or settings.chatgpt_model)
    requested_reasoning_effort = str(
        context.get("job", {}).get("reasoning_effort") or "medium"
    )
    reasoning_effort = (
        "low" if isinstance(context.get("validation_correction"), dict) else requested_reasoning_effort
    )
    if privacy_mode == "local_only":
        revision = context.get("revision")
        if isinstance(revision, dict) and isinstance(revision.get("previous_plan"), dict):
            plan_type = MontageEditPlan if recipe == "montage" else TalkingHeadEditPlan
            return plan_type.model_validate(revision["previous_plan"]), {
                "provider": "local_fixed_revision",
                "model": f"{recipe}_v1",
                "reasoning_effort": None,
                "usage": {},
            }
        planner = deterministic_montage_plan if recipe == "montage" else deterministic_plan
        return planner(
            assets,
            context.get("job", {}).get("target_duration_seconds"),
            context.get("job", {}).get("edit_style") or "clean",
            context.get("job", {}).get("music_mode") or "none",
            context.get("music_library", []),
        ), {
            "provider": "local_fixed_recipe",
            "model": f"{recipe}_v1",
            "reasoning_effort": None,
            "usage": {},
        }

    primary_error: Exception | None = None
    try:
        credentials = usable_chatgpt_credentials(settings)
        document, usage = _request_plan(
            endpoint=OPENAI_RESPONSES_URL,
            token=str(credentials["access_token"]),
            model=selected_model,
            reasoning_effort=reasoning_effort,
            context=context,
            settings=settings,
        )
        plan_type = MontageEditPlan if recipe == "montage" else TalkingHeadEditPlan
        return plan_type.model_validate(document), {
            "provider": "chatgpt_plan",
            "model": usage.get("actual_model") or selected_model,
            "requested_model": selected_model,
            "reasoning_effort": reasoning_effort,
            "usage": usage,
        }
    except ProviderUnavailable as error:
        primary_error = error

    if settings.ai_gateway_fallback_enabled:
        if not settings.ai_gateway_api_key:
            raise ProviderUnavailable(
                "AI Gateway fallback is enabled but AI_GATEWAY_API_KEY is not set"
            ) from primary_error
        document, usage = _request_plan(
            endpoint=GATEWAY_RESPONSES_URL,
            token=settings.ai_gateway_api_key,
            model=settings.ai_gateway_model,
            reasoning_effort=reasoning_effort,
            context=context,
            settings=settings,
        )
        plan_type = MontageEditPlan if recipe == "montage" else TalkingHeadEditPlan
        return plan_type.model_validate(document), {
            "provider": "vercel_ai_gateway",
            "model": usage.get("actual_model") or settings.ai_gateway_model,
            "requested_model": settings.ai_gateway_model,
            "reasoning_effort": reasoning_effort,
            "usage": usage,
        }

    assert primary_error is not None
    raise ProviderUnavailable(
        f"{primary_error} AI Gateway fallback is disabled, so no paid fallback was attempted."
    ) from primary_error
