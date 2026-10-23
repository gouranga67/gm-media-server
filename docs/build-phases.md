# Build phases and live status

Updated: 2026-10-23 (Australia/Brisbane)

This is the working plan for turning the Lenovo into a private media-editing appliance. A phase is complete only when its exit checks pass. Discussion, generated files, and installed packages do not count as a completed phase by themselves.

## Status at a glance

| Phase | Outcome | Status |
|---|---|---|
| 0 | Inventory, content rules, and architecture | Complete |
| 1 | Repository foundation and repeatable diagnostics | Complete |
| 2 | Reproducible local service stack | Complete |
| 3 | Projects, jobs, and resumable phone uploads | In progress |
| 4 | Local ingest and media analysis | Complete |
| 5 | Bounded editor agent and deterministic reel rendering | In progress |
| 6 | Phone review, revisions, delivery, and provenance | Not started |
| 7 | Appliance hardening, backup, and recovery | Not started |

## Phase 0 — inventory and guardrails

**Purpose:** establish what this machine can safely do and define the rule that agents edit supplied media rather than generate new media.

Completed evidence:

- Host, GPU, Docker, Tailscale, SSH, storage, and security posture inspected.
- Docker, containerd, Tailscale, SSH, and NVIDIA host services confirmed healthy after reboot.
- Architecture and workflow recorded in `docs/architecture-plan.md`.
- Synthetic image, video, voice, and music generation excluded from the tool design.

Exit check: the architecture identifies the server limits, trust boundaries, editing workflow, and supported first recipe. **Passed.**

## Phase 1 — repository foundation

**Purpose:** make the build understandable, versionable, and repeatable before adding databases or media services.

Deliverables:

- Repository guide and live phase tracker.
- Runtime pins, secret template, ignore rules, and read-only diagnostic command.
- A clean TypeScript check for the existing Eve/Next.js scaffold under Node 24.
- No credentials, generated media, dependency folders, or build output tracked by Git.

Exit checks:

1. `npm run doctor` accurately reports host and project prerequisites.
2. `npm run typecheck:web` passes using Node 24.
3. `git status --short` shows source files only, with dependencies and generated caches ignored.

Completion evidence (2026-10-22): the host-visible doctor passed with no failures; the three expected warnings are the host Node 22 default, intentionally absent `.env`, and intentionally restricted Docker socket. TypeScript passed under Node 24.22.0, and Git excludes dependency, cache, secret, and media output paths. **Passed.**

## Phase 2 — reproducible local service stack

**Purpose:** define how all application parts start, stop, communicate, and retain data.

Build:

- Docker Compose network with `web-agent`, `api`, `worker`, `tusd`, PostgreSQL, and Redis.
- Health checks, non-root containers, resource limits, persistent volumes, and loopback-only host bindings.
- Initial database migration and API health endpoints.
- A root-managed deployment path so the web application does not receive Docker control.

Exit checks:

1. `docker compose config` passes.
2. All service health checks become healthy after a clean start.
3. A reboot returns the stack to the same healthy state.
4. No application port is exposed beyond loopback or the private Compose network.

Completion evidence (2026-10-22): all images built; migrations and media initialization completed; PostgreSQL, Redis, tusd, API, worker, and web-agent passed their container health checks; the root-managed systemd unit completed a controlled restart; the web health endpoint and home page returned HTTP 200; only `127.0.0.1:3000` was published; and the unit journal contained no warnings. A full machine reboot is deferred to the appliance recovery drill in Phase 7. **Passed.**

## Phase 3 — projects, jobs, and phone uploads

**Purpose:** reliably move original media from the phone into an immutable project record.

Build:

- Project and job schemas with explicit state transitions.
- Installable phone PWA with a New Job flow.
- Private HTTPS entry through Tailscale Serve, proxied to the loopback-only web service.
- Chunked tus uploads with pause/resume and server-side size/type limits.
- SHA-256 registration, safe generated paths, quarantine, and immutable originals.

Current build checkpoint (2026-10-23): the project, job, and asset API is implemented; retries use stable client-supplied IDs so a lost response does not duplicate a record; tusd pre-create hooks enforce registered IDs, sizes, and media families; completed uploads are durably discovered from PostgreSQL, copied to generated original paths, hashed, atomically installed, and recorded as ready; and the browser upload client can resume from stored tus fingerprints. The approved harbor-blue New Job PWA screen is deployed at `/` and `/jobs/new`, with accurate privacy choices, per-file pause/resume/retry, readiness polling, and accessible phone controls. The service and private tailnet-only HTTPS route are healthy. A post-restart acceptance test proved idempotent record retries, interrupted upload offset recovery, resumed transfer, worker finalization, and the expected SHA-256. It also confirmed that the deployed browser bundle uses the canonical `/files` upload endpoint. The software gates pass; one representative large upload interrupted and resumed from a physical phone remains before this phase can pass its written exit check.

Exit check: a multi-gigabyte phone upload can be interrupted, resumed, verified, and attached to a project without duplication.

## Phase 4 — local ingest and analysis

**Purpose:** turn uploaded files into structured facts the editor can use.

Build:

- ffprobe validation and normalized proxies.
- Local transcription with timestamps.
- Scene boundaries, thumbnails, contact sheets, audio levels, blur scores, and orientation metadata.
- One-job GPU concurrency with CPU fallback and durable retries.

Completion evidence (2026-10-23): a dedicated worker image packages pinned FFmpeg, CUDA/cuDNN, faster-whisper, and a pinned local Whisper Small model. PostgreSQL owns a leased ingest queue, startup immediately reclaims orphaned work, and ordinary failures receive at most three bounded attempts. The worker produces a normalized technical probe, orientation, H.264 proxy, thumbnails, contact sheet, scene markers, sampled sharpness, loudness, timestamped transcript, WebVTT captions, and a source-only manifest. Derived files are atomically installed read-only; filenames never become paths; and low-space guards stop new analysis below 50 GiB or 15% free. Backend unit tests, Python compilation, Compose validation, TypeScript, and the production web build passed. The live container deployment confirmed the RTX 3050, CUDA driver interface, FFmpeg, and all service health checks. A real 17.67-second phone clip produced every required artifact; its proxy used `h264_nvenc`, its loudness and nine-frame sharpness samples were measured, and its manifest recorded `synthetic_media: false`. The recovery drill killed the worker after it durably claimed that clip; the replacement reclaimed it and completed successfully on attempt 2. **Passed.**

Acceptance helper after deployment: `python3 scripts/verify-phase4.py` selects the newest finalized real audio/video asset, waits for analysis, and validates the manifest. Pass `--asset-id UUID` to target a particular clip.

Recovery helper: `sudo ./scripts/verify-phase4-restart.sh` requeues an already analyzed real asset, kills the worker only after it has durably claimed the task, starts a replacement worker, and requires the recovered attempt to finish successfully.

Exit check: a real phone clip produces a proxy, transcript, thumbnails, and analysis manifest, and resumes correctly after a worker restart. **Passed.**

## Phase 5 — bounded editor and deterministic rendering

**Purpose:** let an agent make editorial choices without giving it the ability to create synthetic media or execute arbitrary commands.

Build:

- Narrow Eve tools for inspecting project facts and submitting edit decisions.
- Versioned edit-decision-list schema referencing source asset IDs and timecodes only.
- Talking-head recipe with source-led cuts, vertical crop, captions, audio normalization, and approved title/end-card templates.
- Schema, provenance, duration, source-range, and effect allow-list validation before rendering.

Current build checkpoint (2026-10-23): the source tree now contains a durable PostgreSQL edit queue, a strict versioned talking-head EDL, independent source/range/duration validation, and a renderer whose FFmpeg arguments are assembled exclusively by trusted code. The first preview profile is 540 × 960 H.264 with source-derived captions, spoken-word loudness normalization, NVENC with a CPU fallback, atomic read-only outputs, and a provenance manifest. The editor uses ChatGPT plan usage through a private Sign in with ChatGPT credential; local-only projects use a fixed recipe, and Vercel AI Gateway is a disabled-by-default safety net. Eve's general shell/filesystem/web tools are disabled and its three project tools are limited to inspecting a job, requesting a preview, and submitting the same validated EDL. The phone flow can start editing, poll the durable run, play the preview, and download its MP4.

Deterministic acceptance evidence (2026-10-23): migration 005 deployed with every production service healthy. The live Phase 5 verifier used analyzed phone footage, proved an invented asset ID returns HTTP 422, rendered preview version 1 with `h264_nvenc`, and successfully downloaded a valid MP4 through the phone-facing web proxy.

The deterministic production acceptance check has passed on real analyzed footage. This phase remains in progress until a live ChatGPT-planned preview is reviewed for editorial coherence.

Exit check: the agent creates a valid plan from uploaded footage and the deterministic renderer produces a coherent preview. An invalid or invented asset reference is rejected.

## Phase 6 — review, revisions, and delivery

**Purpose:** complete the workflow from phone brief to approved download.

Build:

- Mobile job timeline and progress events.
- Preview player, caption correction, approval, and bounded revision flow.
- 1080 × 1920 H.264 export, cover image, captions, and optional approved post copy.
- Provenance manifest containing hashes, source ranges, models, tool versions, template version, render settings, and QA results.

Exit check: from a phone, upload a clip, request a reel, approve or revise it, and download a technically valid final package.

## Phase 7 — appliance hardening and recovery

**Purpose:** make the Lenovo reliable enough to hold important footage and recover from failures.

Build:

- Tailscale identity-bound application sessions and trusted-proxy header enforcement.
- Disk, temperature, queue, job-failure, SMART, and backup-age monitoring.
- Retention policies and storage-pressure protections.
- Encrypted backup of originals, database, templates, and exports to a second device or storage provider.
- Restore drill and written recovery procedure.

Exit check: reboot during a render, restore service automatically, finish the job, and restore a deleted test project from backup.
