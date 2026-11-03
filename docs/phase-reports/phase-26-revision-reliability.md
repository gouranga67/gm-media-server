# Phase 26 — dependable stories and revisions

Source checkpoint: 2026-11-03 UTC. Implemented locally; owner deployment and real-footage acceptance remain pending. The owner confirmed the direct subtitle editor works well. This checkpoint is part of the larger [26–31 build sequence](../build-phases.md#active-large-build-phases--2631), not completion of every story-quality goal in Phase 26.

## Result

Exact quoted speech requests are resolved against the saved audible source words before a revision is queued. `Make "cream works" louder by 3 dB` adds bounded gain to that interval. `Shorten the pause after "cream works" to 0.5 seconds` measures the following source gap and removes only verified quiet audio, keeping word margins and non-quiet reactions. Substitute actual recorded words. Matching normalises case/punctuation but does not guess words or substitute corrected subtitle spelling.

Missing/ambiguous quotes explain the limitation without queueing or using an editor call. Add `in clip 2` for occurrences in different clips; quote a longer unique passage or use precise controls if it repeats inside the same clip. Pause inspection is limited to one gap of at most 20 seconds with a three-second decode timeout. Independent J/L audio joins require the precise controls. Mixed instructions and unsupported prose keep the existing planner route.

Migration 043 stores the validated result and immutable parent/document hashes on the pending run. The worker replays it without another model request or source measurement, including after a render interruption. Failed local validation does not fall back to a hosted repair. The request and duration settings are tied to the version the user reviewed. Local-only projects can use these supported commands.

The review receipt names the matched phrase, source clip, changed interval and actual pause retained; **Listen at** seeks without autoplay or queueing. Rejected requests preserve the typed note. Nothing is submitted while typing.

## Preservation and story review

Phrase gain adds to saved automatic take balance rather than disabling balance throughout the reel. Deterministic local changes retain saved audio-cleanup decisions. Explicit automatic-cleanup requests still perform their requested inspection. Final loudness limiting remains active, so human listening judges the perceptual gain.

A verified quiet cut retimes saved subtitle corrections, hidden state and positions through the surviving timeline. General story rebuilding still resets custom subtitles when their source basis changes. Existing precise timeline rules retime later camera, graphic and audio cues. Originals, prior plans, transcripts, approvals and cached library analysis are preserved.

The recorded story outline now reports distinct available/selected speech recordings and supporting picture sources. A conservative omitted-qualifier hint flags a nearby excluded word such as “not” or “only” for listening. It does not repair meaning automatically. Counts are not selection quotas; using every uploaded source does not establish a good story. No new ad structure is imposed.

## Verification

- 629 backend tests passed, including actual CPU FFmpeg gain-window renders, quiet-versus-tone inspection, timing/gain limits, caption remapping, local-only/stale/ambiguous preflight and immutable replay. Worker tests cover fresh and resumed renders plus invalid-local rejection without a hosted fallback.
- 71 UI interaction tests passed; web and agent TypeScript, production build, Python compilation, Compose configuration, public-release audit and patch checks passed through all eight source-suite gates.
- A disposable PostgreSQL-compatible database applied all 43 migrations and ran the actual 18-parameter queue SQL. It verified stored resolution round-trip, parent immutability, schema readiness and the JSON-object constraint. No production database was used.
- An isolated built-app browser check used synthetic preview/data at desktop 1280px and phone 390px: no horizontal overflow, 44px seek target, no submit while typing, displayed version sent, rejection retains text, explicit resubmission clears it, and seeking stays paused. The expected mocked 422 is not an application failure.

No production deployment, user-job mutation, hosted edit call, rule promotion or social post was performed. These tests establish execution behavior, not semantic story quality, humour, restoration quality or live NVENC throughput.

## Deploy and accept

```bash
cd /path/to/gm-media-server
sudo ./scripts/install-service.sh
python3 scripts/verify-phase26.py
```

The helper and new live-suite readiness gate are read-only. Use the [grounded revision acceptance checklist](../testing-plan.md#grounded-revision-acceptance--2026-11-03) for the real-footage phrase, pause, subtitle-preservation, export and multi-source story pass. Complete those checks before marking Phase 26 fully accepted. The next large delivery is better context and evidence-backed bloopers; visual finishing, library intake, evaluated learning and publishing/release acceptance follow in that order.
