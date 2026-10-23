# Build phases and live status

Updated: 2026-10-24 (Australia/Brisbane)

This is the working plan for turning the Lenovo into a private media-editing appliance. A phase is complete only when its exit checks pass. Discussion, generated files, and installed packages do not count as a completed phase by themselves.

## Status at a glance

| Phase | Outcome | Status |
|---|---|---|
| 0 | Inventory, content rules, and architecture | Complete |
| 1 | Repository foundation and repeatable diagnostics | Complete |
| 2 | Reproducible local service stack | Complete |
| 3 | Projects, jobs, and resumable phone uploads | In progress |
| 4 | Local ingest and media analysis | Complete |
| 5 | Bounded editor agent and deterministic reel rendering | Complete |
| 6 | Phone review, revisions, delivery, and provenance | Complete |
| 6A | Creative duration, motion, transitions, and licensed music | Complete |
| 6B | Montage recipe, model controls, and usage visibility | Complete |
| 6C | Reusable on-server content library | Planned |
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

Completion evidence (2026-10-23): the deterministic production acceptance check passed on real analyzed footage, and a live ChatGPT-plan edit produced a valid, coherent preview that was positively reviewed from the phone interface. **Passed.**

Exit check: the agent creates a valid plan from uploaded footage and the deterministic renderer produces a coherent preview. An invalid or invented asset reference is rejected.

## Phase 6 — review, revisions, and delivery

**Purpose:** complete the workflow from phone brief to approved download.

Build:

- Mobile job timeline and progress events.
- Preview player, caption correction, approval, and bounded revision flow.
- 1080 × 1920 H.264 export, cover image, captions, and optional approved post copy.
- Provenance manifest containing hashes, source ranges, models, tool versions, template version, render settings, and QA results.

Completion evidence (2026-10-24): the deployed phone workflow completed a ChatGPT-planned revision and recovered its initially failed final export without another planning call. The accepted version rendered with NVENC at 1080 × 1920, and the live verifier downloaded and validated its MP4, WebVTT captions, JPEG cover, ZIP package, provenance manifest, source-policy record, and technical QA. **Passed.**

Acceptance helper after deployment: `python3 scripts/verify-phase6.py` selects a ready preview, requests one bounded revision, approves the new version, waits for the final GPU render, and verifies the MP4, captions, cover, package, provenance, and source-only policy.

Exit check: from a phone, upload a clip, request a reel, approve or revise it, and download a technically valid final package.

## Phase 6A — bounded creative editing grammar

**Purpose:** make talking-head reels feel intentionally edited while keeping every model decision inside a small, auditable vocabulary.

Build:

- Phone controls for 20/30/45/60-second targets, must-include points, target platform, Clean/Energetic/Calm styles, and optional music level.
- EDL 1.1 presets for standard framing, two bounded punch-ins, slow push/pull, hard cuts, and short dip-to-black transitions.
- Trusted FFmpeg implementation of every preset; models cannot submit expressions, filters, paths, zoom factors, or mix levels.
- A local music catalogue requiring an operator-supplied file, SHA-256, licence URL and proof record, commercial-use confirmation, attribution, and explicit platform scope.
- Automatic speech normalization, music trimming/fades, and side-chain ducking. Music remains off by default and the agent cannot browse for or download tracks.

Completion evidence (2026-10-23): the production phone flow generated a positively reviewed talking-head edit from a clear direction brief using bounded duration, motion, transition, and music controls. Existing EDL 1.0 plans and jobs remain valid; creative constraints apply to newly directed jobs without rewriting historical versions. **Passed.**

Exit check: from the phone, request a 45-second energetic reel from sufficiently long footage, observe bounded visual emphasis and at least one transition, and confirm a rights-approved test track ducks under speech only when music is explicitly enabled.

## Phase 6B — montage, model controls, and usage visibility

**Purpose:** support a second useful editing recipe and make the hosted editor's resource use understandable from the phone.

Build:

- Phone-selectable Montage recipe for uploaded video and photos, with 15/30/45/60-second targets and vertical or landscape delivery.
- Strict montage EDL containing source asset IDs, bounded source ranges, fixed transition/motion presets, and optional approved-library music only.
- Deterministic local FFmpeg preview and full-resolution renderer with NVENC and CPU fallback; the model chooses the edit but never renders or generates media.
- Account-specific model catalogue from the connected ChatGPT account, a per-job model selector, and Low/Medium/High reasoning control.
- Durable per-request token ledger recording input, cached input, output, reasoning, total tokens, and latency.
- Per-job usage on the review/download screen plus a 30-day model usage screen.
- Local beat-grid analysis for operator-imported rights-approved music, used as timing context rather than as generated content.

Completion evidence (2026-10-24): the deployed verifier refreshed an approved legacy montage through the current renderer without another planning request. The vertical final used `h264_nvenc`, included five source-speech caption events, exposed its WebVTT captions and phone download, and preserved the approved edit as version 3. The connected ChatGPT account returned seven selectable models; the verified run recorded `gpt-6.1-sol` at medium reasoning with 68,281 measured tokens, while the all-time dashboard reported 17 requests across 16 jobs. **Passed.**

Planning recovery now records every hosted request immediately and allows one low-effort correction when an otherwise schema-valid plan fails deterministic validation. The correction receives the exact validator error and rejected plan, while all source, overlap, duration, music, and effect constraints remain unchanged.

Montage stills render from the clean, metadata-stripped JPEG derivative created during ingest. This avoids malformed phone-camera APP metadata breaking a multi-input FFmpeg render, reduces decode cost, and preserves the immutable original hash as the provenance source.

Acceptance helper after deployment and one approved montage: `python3 scripts/verify-phase6b.py` verifies the account model catalogue, per-job and 30-day usage ledgers, final montage dimensions, MP4, ZIP package, and manifest.

Exit check: select at least two real videos/photos on the phone, request a montage, review it, approve it, download the final package, and confirm that its job screen displays the selected model and non-negative measured token totals. **Passed.**

## Phase 6C — reusable on-server content library

**Purpose:** stop re-uploading footage that the Lenovo already holds, without copying or weakening ownership and deletion rules.

Planned build:

- A searchable **Server library** beside the phone file picker, with thumbnails, source names, dates, media type, duration, project, and analysis readiness.
- An explicit **Attach to this job** operation that adds a database reference to an existing original; it does not copy the media bytes.
- SHA-256 duplicate detection so a repeated upload can offer the existing item rather than silently storing another full original.
- Clear **remove from job**, **archive**, and **delete original** semantics. Detaching a job never deletes the original; deleting the final retained library item requires confirmation and later backup coverage.
- Filters for recent footage and prior projects, which directly addresses repeated testing with similar clips.

This is deliberately after Phase 6B. The current schema makes an asset belong to one project, so a safe cross-project library needs a small ownership migration rather than a UI shortcut that could cascade-delete shared originals.

## Phase 7 — appliance hardening and recovery

**Purpose:** make the Lenovo reliable enough to hold important footage and recover from failures.

Build:

- Tailscale identity-bound application sessions and trusted-proxy header enforcement.
- Disk, temperature, queue, job-failure, SMART, and backup-age monitoring.
- Retention policies and storage-pressure protections.
- Encrypted backup of originals, database, templates, and exports to a second device or storage provider.
- Restore drill and written recovery procedure.

Exit check: reboot during a render, restore service automatically, finish the job, and restore a deleted test project from backup.
