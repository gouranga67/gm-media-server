# Build phases and live status

Updated: 2026-10-26 (Australia/Brisbane)

This is the working plan for turning the Lenovo into a private media-editing appliance. A phase is complete only when its exit checks pass. Discussion, generated files, and installed packages do not count as a completed phase by themselves.

## Status at a glance

| Phase | Outcome | Status |
|---|---|---|
| 0 | Inventory, content rules, and architecture | Complete |
| 1 | Repository foundation and repeatable diagnostics | Complete |
| 2 | Reproducible local service stack | Complete |
| 3 | Projects, jobs, and resumable phone uploads | Complete |
| 4 | Local ingest and media analysis | Complete |
| 5 | Bounded editor agent and deterministic reel rendering | Complete |
| 6 | Phone review, revisions, delivery, and provenance | Complete |
| 6A | Creative duration, motion, transitions, and licensed music | Complete |
| 6B | Montage recipe, model controls, and usage visibility | Complete |
| 6C | Reusable on-server content library | Complete |
| 6D | Searchable scene, phrase, and media catalogue | Complete |
| 6E | Local semantic visual indexing and hybrid library search | Complete |
| 6E.1 | Denser visual evidence sampling and relevance-ranked search | Complete |
| 7 | Appliance hardening, backup, and recovery | Complete |
| 8 | Managed media memory, collections, and reversible cleanup | Complete |
| 9 | Safe exact-copy cleanup and automatic storage reuse | Complete |
| 10 | Creative profiles and local delivery variants | Complete |
| 11 | Editorial workspace and brand system | Complete |
| 12 | Product dashboard, access, budgets, and retention | Source complete; live acceptance pending |
| 17A | Local rendered-quality reports with zero hosted AI usage | Source complete; live acceptance pending |
| 18 | Optional High impact style, rhythmic framing, and picture-only B-roll | Source complete; live acceptance pending |

The current improvement-loop increment is Phase 17A: inspect the rendered file and retain a versioned report without changing the edit. Planned follow-ups are targeted, reversible repairs for verified faults; budgeted AI review of story and delivery; and evaluating candidate editing preferences against saved examples and human ratings before adopting them. These follow-ups are not implemented by the report-only increment.

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
- Per-clip source-audio gain for exact dialogue emphasis, with automatic music ducking under audible montage clips and backward-compatible playback of older plans.
- Deterministic selection of an approved music track when the model omits that predictable field, avoiding a second model request for that repair.
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

Current build checkpoint (2026-10-24): the approved phone design has been implemented in the source tree. The New Job screen can switch between resumable uploads and a searchable server library, filter analyzed originals by media type or originating project, preserve mixed selections across tabs, and show thumbnails and selection totals. The API lists only active, fully analyzed originals and attaches selections to a draft job through the existing `job_assets` reference table; repeated attachment is idempotent and no media bytes or hashes are copied. Migration 010 changes the originating-project foreign keys from cascade deletion to restricted deletion, so a reusable original cannot disappear through an unrelated project cleanup.

The approved exact-duplicate audit is also implemented in the source tree at `/library/duplicates`. It groups only active, fully analyzed originals with the same verified SHA-256, reports redundant copies and reclaimable bytes, exposes every filename/project/upload date/job-reference count, and recommends a canonical record using job references followed by original age. A review stores only that canonical preference; it never deletes, merges, moves, or rewrites media. Reviews automatically become stale when another identical original joins the group, forcing the changed group back through review. Migration 011 adds the small review ledger and a partial hash index; `scripts/verify-phase6c2.py` verifies the live audit, byte calculation, checksum validation, and non-destructive review round trip. TypeScript, the production Next.js build, Python compilation, Compose configuration, and source checks pass. Deployment and both live Phase 6C acceptance helpers remain outstanding.

Planned build:

- A searchable **Server library** beside the phone file picker, with thumbnails, source names, dates, media type, duration, project, and analysis readiness.
- An explicit **Attach to this job** operation that adds a database reference to an existing original; it does not copy the media bytes.
- SHA-256 exact-duplicate detection and read-only canonical review. A future upload-time shortcut can offer the existing item before retained-storage cleanup is enabled.
- Clear **remove from job**, **archive**, and **delete original** semantics. Detaching a job never deletes the original; deleting the final retained library item requires confirmation and later backup coverage.
- Filters for recent footage and prior projects, which directly addresses repeated testing with similar clips.

Completion evidence (2026-10-24): migrations 010–011 deployed cleanly and the live suite found 76 analyzed originals. It attached an existing original to the stable verification job without copying its storage key or SHA-256, proved the repeated attachment was idempotent, and downloaded its valid JPEG thumbnail. The exact-hash audit found 13 duplicate groups containing 59 redundant records and calculated 1,172,262,842 potentially reclaimable bytes. It stored and reread a canonical preference while confirming that no media file changed. The production CUDA worker also passed all duplicate, schema, renderer, ingest, upload, and editing unit tests. **Passed.**

An upload-time reuse shortcut plus explicit archive/delete controls remain Phase 7 retention work because they change retained storage, while the current workflow deliberately preserves every original.

Acceptance helper after deployment: `python3 scripts/verify-phase6c.py` creates a local-only draft job, attaches one analyzed original twice, proves the second request is idempotent, confirms the new job still references the original storage key and SHA-256, and validates its library thumbnail when available.

Exact-duplicate acceptance helper after deployment: `python3 scripts/verify-phase6c2.py` checks the audit summary, verifies every reported copy and reclaimable-byte calculation, records the recommended canonical item, confirms the review is visible on the next read, and proves an invalid checksum is rejected.

## Phase 6D — searchable content intelligence

**Purpose:** let future editing agents find a spoken phrase, subject, shot, or reusable moment without repeatedly inspecting whole files or inventing media descriptions.

Current build checkpoint (2026-10-24): migration 012, the durable catalogue worker, local full-text API, phone-library phrase search, and two bounded Eve tools are implemented in the source tree. Existing analyzed assets are queued for a restart-safe backfill; new analyses queue indexing automatically. Catalogue rows contain immutable asset IDs, exact source ranges, transcript text, detected scene ranges, technical facts, and the tool/model that produced each fact. Reviewed exact duplicates collapse to their canonical asset during search, while stale or unreviewed groups remain visible. The agent can search this evidence and can attach selected originals to a draft job only through the existing validated API; attachment requires explicit Eve human approval. No generated description, arbitrary filesystem path, shell, or external search capability was added.

Planned build:

- A durable segment catalogue tied to immutable asset IDs and time ranges: transcript utterances, detected scenes, image facts, and later OCR text.
- Local full-text search first, followed by source-derived semantic embeddings when their model, dimensions, and re-index procedure are pinned.
- Search results that always return the original asset, exact time range, project, thumbnail, and the evidence that caused the match.
- Bounded agent tools for searching and attaching catalogue results. The editor may select existing source segments but cannot alter catalogue facts or create synthetic footage.
- Re-index and provenance records so a better transcription or vision model can improve the catalogue without changing the original media or hiding which model produced a tag.
- A library review surface for correcting titles/tags and hiding weak suggestions while retaining the machine-derived evidence.

This follows the exact-duplicate audit: duplicate groups need stable canonical records before multiple copies can otherwise create repeated search results and waste future indexing work.

Completion evidence (2026-10-24): migration 012 deployed and the restart-safe worker catalogued all 76 analyzed originals into 379 source-evidence records: 173 timestamped transcript utterances, 109 FFmpeg scene intervals, plus asset/image facts. The live search returned the verified source asset, exact range, and evidence model, rejected a blank query, and recorded that no synthetic descriptions were produced. The pinned CUDA worker passed the catalogue tests as part of a 61-test backend suite. **Passed.**

OCR and optional hosted visual descriptions remain later opt-in enrichments. Phase 6D by itself does not claim that filenames or FFmpeg scene boundaries are semantic visual understanding; Phase 6E adds that understanding locally without generated descriptions.

The comprehensive acceptance sequence is documented in `docs/testing-plan.md`. Its source, live-core, and render/AI lanes passed on 2026-10-24: all 10 automated live gates and 61 backend tests passed. The physical-phone lane remains to exercise the complete Phase 3–6 user journey from the actual device.

Acceptance helper after deployment: `python3 scripts/verify-phase6d.py` waits for the durable backfill, requires zero failed catalogue assets, searches for a real library item, validates its source/time/model evidence, and proves blank queries are rejected.

## Phase 6E — local semantic visual indexing

**Purpose:** make searches such as “fighter jet,” “person walking,” or “car in the woods” find what is visible in source footage, while keeping media private and retaining exact source evidence.

Current build checkpoint (2026-10-24): the source implementation is complete and ready to deploy. A private `visual-indexer` container runs the pinned `openai/clip-vit-base-patch32` image/text encoder locally, with GPU acceleration and no host port. The durable worker samples one to three representative JPEGs from every detected scene, stores normalized 512-dimensional embeddings with the exact asset, scene, timestamp, model revision, and source-frame path, and resumes safely after restarts. It processes one asset per worker loop so indexing an existing library does not starve previews or final exports.

Reviewed exact duplicates share one canonical visual index. The library and search API suppress confirmed redundant copies while automatically returning to separate records if a duplicate review becomes stale. Text and visual evidence are merged into one result per source item; visual-only matches display the actual indexed frame and time range, never an invented scene description. The browser polls local backfill progress and continues to provide filename/transcript search if the visual encoder is unavailable.

The first implementation deliberately stores vectors as PostgreSQL `real[]` values and scores them in the API. That is simple and inspectable for this personal library size. A vector extension or approximate index is an upgrade path only if measured search latency becomes a problem at much larger scale.

Source checks cover canonical assignment, keyframe sampling, cosine scoring, Python compilation, TypeScript, production web build, Compose configuration, and the bounded Eve tool contract. Live deployment must still prove that the pinned model loads on this RTX 3050, backfills the canonical library without failures, and returns the known fighter-jet scene with a valid source JPEG.

Acceptance helper after deployment: `python3 scripts/verify-phase6e.py` waits for the restart-safe backfill, requires zero failures and local-only inference, searches for “fighter jet,” validates the returned source range and JPEG evidence, rejects duplicate hashes, and confirms that no synthetic visual description was stored.

## Phase 6E.1 — visual search quality pass

**Purpose:** improve recall and presentation quality before the media catalogue becomes the main way an editor finds reusable footage.

Current source checkpoint (2026-10-24): each scene is sampled at roughly 1.5-second intervals with even temporal coverage, capped at 48 frames per scene and 120 per canonical original. Search now drops the weak long tail relative to the strongest match, caps results at eight, and presents actual similarity order in the browser. The visual index version is now 1.1, so the durable worker automatically refreshes older indexes after deployment. No hosted vision model or generated description was added.

Exit check: after the 1.1 backfill completes, “fighter jet” returns the known plane source among the strongest results with a correct local JPEG and time range, while unrelated low-score originals are absent.

## Phase 7 — appliance hardening and recovery

**Purpose:** make the Lenovo reliable enough to hold important footage and recover from failures.

Build:

- Tailscale identity-bound application sessions and trusted-proxy header enforcement.
- Disk, temperature, queue, job-failure, SMART, and backup-age monitoring.
- Retention policies and storage-pressure protections.
- Encrypted backup of originals, database, templates, and exports to a second device or storage provider.
- Restore drill and written recovery procedure.

Current checkpoint (2026-10-24): the prepared 64 GB USB is pinned by filesystem UUID and mounted at `/mnt/gm-backup`. The root-run, encrypted Restic 0.19.1 backup captures consistent PostgreSQL dumps, immutable media, protected ChatGPT credentials, and application source/configuration. It applies a 7-daily/5-weekly/12-monthly retention policy, samples stored data during every backup check, and records machine-readable status. The first repository check passed, and the isolated recovery drill restored and validated the database plus all 3.086 GiB in the full snapshot, including 78 original media files, without mounting or altering the live media volumes. The restore repository remains read-only and the drill shares a host lock with nightly backup/pruning. After the initial key was exposed, the repository password was rotated and the replacement recovery key was saved externally in the owner's password manager. A persistent nightly systemd timer and a five-minute appliance-health timer are installed. The health snapshot reports storage pressure, GPU temperature, core services, queue depth, recent render failures, SMART availability, and backup age through a read-only `/system` screen; the application still receives no Docker socket or device access.

The remaining Phase 7 source is now implemented. `configure-private-access.sh` binds the web layer to the Tailscale owner identity supplied by private Serve while keeping the container port on host loopback. A pinned rclone tool container and root-only importer mirror only the encrypted Restic repository to OneDrive after the local backup, verify the remote file set, preserve displaced objects for 90 days, and publish separate USB/off-site status to `/system`. A boot-enabled recovery verifier can reuse a persisted verification edit plan, deliberately reboot during rendering, and require the worker to resume it into a readable preview without another model request.

Completion evidence (2026-10-24): Tailscale owner enforcement accepted the configured owner and rejected direct unauthenticated requests. The encrypted OneDrive mirror completed with 70 matching repository files and zero differences, then passed its retention cleanup. The deliberate reboot drill interrupted an active render, changed the machine boot ID, recovered the durable run on the first attempt, and produced a readable preview after startup. **Passed.**

Exit check: reboot during a render, restore service automatically, finish the job, and restore a deleted test project from backup.

## Phase 8 — managed media memory

**Purpose:** turn analyzed originals into a clean, durable content memory that can be searched and reused across future editing jobs.

Current source checkpoint (2026-10-24): migration 014 adds user-owned display names, notes, favorites, normalized tags, and collections without altering original hashes or paths. The new `/library` UI combines metadata search with transcript and local CLIP-frame results, keeps strongest evidence ordering, previews the existing original/proxy, exposes timestamped speech/scene evidence and representative source frames, and supports collection membership. Archive/restore is reversible. Permanent deletion is deliberately absent and visibly locked until the encrypted backup passes its restore drill. `scripts/verify-phase8.py` round-trips metadata, a temporary collection, archive/restore, and preview download while restoring the original record and deleting no media.

Live acceptance evidence (2026-10-24): migration 014 deployed successfully and the managed-library verifier preserved the selected original's SHA-256 while round-tripping metadata, collection membership, archive/restore, and preview download with zero deleted originals. The complete regression and render suite then passed 13/13 gates across container health, 61 backend tests, analysis, reusable media, exact duplicates, transcript and visual search, job history, deterministic GPU rendering, talking-head delivery, montage delivery, captions, measured model usage, and phone-download endpoints. **Automated gates passed.**

Exit check: deploy migration 014, pass the live Phase 8 verifier, confirm search and editing on a phone, then unlock canonical duplicate cleanup only after the Phase 7 restore gate passes.

## Phase 9 — safe exact-copy cleanup and automatic reuse

**Purpose:** reclaim storage from confirmed byte-for-byte duplicates without breaking historical jobs, library records, project provenance, or download paths.

Current source checkpoint (2026-10-24): migration 015 records every physical-storage optimization with the source asset, reviewed canonical asset, verified SHA-256, storage keys, filesystem identity, reason, and reclaimed byte count. The duplicate audit now separates canonical review from cleanup, shows already optimized copies, and requires an explicit confirmation before changing storage.

Cleanup hashes the canonical and every redundant original immediately before acting. It then atomically replaces the redundant file with a hard link to the verified canonical bytes. Both original paths, all asset IDs, filenames, projects, job references, edit plans, metadata, previews, and search evidence remain valid. A mismatch, missing path, cross-filesystem copy, or stale group review stops safely before that copy is changed. No database record or unique original is deleted.

New uploads receive the same storage optimization automatically after their completed bytes are hashed and matched to an existing ready original. Upload records and project provenance remain separate, while identical content occupies one set of physical blocks. Selecting an existing library item remains the way to avoid transferring the file again over mobile data.

Source verification covers atomic replacement, checksum refusal, idempotent already-shared storage, audit calculations, Python compilation, TypeScript, and production web build.

Exit check: deploy migration 015, run `python3 scripts/verify-phase9.py --confirm-storage-optimization`, confirm the reviewed group reports zero remaining reclaimable bytes, open an existing job and library preview that used a redundant asset, then run the complete live suite. No library record may be deleted.

## Phase 10 — creative profiles and local delivery variants

**Purpose:** turn a successful edit into a reusable house style and produce channel-specific versions without paying for another editorial model call.

Current source checkpoint (2026-10-24): migration 016 adds named Creative Profiles containing the recipe, target duration, editing style, music level, platform, output shape, and reasoning effort used by a delivered job. The final-delivery screen can save these settings, and the new-job screen can apply a profile while keeping every field editable.

An approved edit can now create durable vertical, landscape, or square delivery variants at 15, 20, 30, 45, or 60-second caps. The worker derives a prefix cut from the frozen plan, preserves its source order and provenance, rerenders locally with FFmpeg/NVIDIA, includes captions, cover, manifest, and ZIP package, and records `derived_without_model_call: true`. Variant queues recover after restarts and do not change the job's AI usage ledger. Talking-head previews and finals now respect all three output shapes as well.

Acceptance helper after deployment: `python3 scripts/verify-phase10.py` saves and removes a temporary profile from an existing delivered job, creates a square 15-second local variant, downloads its ZIP, validates its 1080 × 1080 manifest and zero-model provenance, and confirms the job token count did not change.

Completion evidence (2026-10-24): migration 016 deployed successfully. The live verifier round-tripped a Creative Profile from delivered job `aa8269b5`, rendered square variant `5a553d19` at a 15-second cap, downloaded its package through the phone endpoint, and measured zero additional model tokens. **Passed.**

Exit check: deploy migration 016, pass the Phase 10 helper, apply a saved profile to a fresh phone job, then download one locally derived variant package.

## Phase 11 — editorial workspace and brand system

**Purpose:** expose the source-led edit plan in plain language, make precise revisions without repeated model calls, and keep recurring output visually consistent.

Current source checkpoint (2026-10-24): migration 017 adds managed Brand Kits, publishing presets, cover-frame selection, locked revision elements, and persisted clip adjustments. The review screen lists every selected source with its source range, assembled duration, transcript excerpt, transition, framing move, and source-audio level. A user can reorder or remove clips, change emphasis, and raise or lower montage source sound; these operations derive a new validated plan and render locally with zero additional model usage. Free-text revisions can protect clip order, spoken phrases, captions, and music from model changes.

The new Brand & Presets screen creates and edits caption colours, weight, and a safe bundled typeface; it also renames, duplicates, and removes Creative Profiles. New jobs can apply a named brand kit and deterministic Instagram, TikTok, YouTube, LinkedIn, or Facebook publishing preset. Brand settings flow into preview and final ASS captions and are recorded in provenance. Final approval accepts an explicit cover-frame timestamp, and completed delivery variants can be played beside the original before downloading.

Acceptance helper after deployment: `python3 scripts/verify-phase11.py` round-trips a temporary brand kit, creates and renames a profile carrying brand/publishing provenance, and confirms an existing real job exposes a source-backed editorial timeline. It cleans up its temporary records and makes no model request.

Exit check: deploy migration 017, pass the Phase 11 helper and complete live suite, create one branded montage, make a clip-level local adjustment, confirm the token count is unchanged, approve it with a selected cover frame, and compare one delivery variant in the browser.

## Phase 12 — productization and safe collaboration

**Purpose:** turn the private appliance into a coherent product that is understandable on first use, manageable over time, and safe to share with a small trusted team.

Current source checkpoint (2026-10-24): migration 018 adds a single-owner Tailscale membership directory with editor and viewer roles, appliance settings, an operator audit, job archiving, and retention-run provenance. The existing Tailscale owner is bootstrapped automatically and remains immutable through the application. Invited identities must already belong to the tailnet. Viewers are read-only at the web boundary; editors can create and revise work; access, budgets, and cleanup remain owner-only.

The root screen is now a concise studio dashboard. Guided onboarding reports private access, editor connection, backup monitoring, brand readiness, library readiness, and first delivery. A dedicated job workspace searches all work, explains its current status, and archives or restores records without deleting history. Operations exposes measured daily/monthly tokens, optional hard model-call budgets, active-job concurrency, storage categories, preview/export retention, and recent administrative actions.

Retention deliberately excludes originals. It can remove only reproducible preview and delivery files after configured age thresholds, preserves plans, provenance, usage, metadata, and job history, and records a run whose `originals_removed` value is constrained to zero by PostgreSQL. Missing previews can be rebuilt from their saved plan, and an expired final can be regenerated after its preview is restored. Default retention is 30 days for previews and 90 days for deliveries; token limits default to unlimited.

Acceptance helper after deployment: `python3 scripts/verify-phase12.py` bootstraps the configured owner, round-trips a temporary viewer/editor, raises and restores token thresholds, archives and restores an idle real job, runs retention with 10-year thresholds, confirms the operator audit, and requires zero removed originals and zero additional model tokens.

Exit check: deploy migration 018, pass the Phase 12 helper and full core suite, complete the onboarding screen, archive and restore one job from a phone, and review Operations before inviting another tailnet user.

## Phase 13 — story intelligence and viewer engagement

**Purpose:** help the editor build a deliberate story from reusable local evidence while keeping hosted model use to one bounded planning request.

Current source checkpoint (2026-10-25): migration 019 adds explicit audience, story goal, desired feeling, and ending direction to each job. The durable catalogue worker builds and caches source-timestamped moment cards from local Whisper segments and FFmpeg scene boundaries. Local retrieval ranks those moments against the brief and story direction while retaining opening and closing evidence; no hosted analysis call is made. Phase 13B enriches those cards with speech cadence, pauses, transcription confidence, specificity, hook/payoff/reaction strength, scene pace, measured sharpness, and clean edit-point guidance. Existing catalogues are automatically refreshed to version 1.2 and story index 1.1 after deployment.

Phase 13C hardens the physical edit around those decisions. Long Whisper segments are divided into short word-timed caption cards, audible clip selections receive small source-backed handles around the first and last word, and voice-only revisions deterministically discard any model-selected music. Timeline controls now stage one change for explicit confirmation before creating a local preview. Resumable uploads use smaller adaptive chunks on ordinary and constrained connections and display measured throughput, estimated time remaining, and retry state.

Phase 13D improves delivery fidelity for phone footage. HDR10 and HLG sources are detected from their technical metadata and tone-mapped locally into explicitly tagged BT.709 SDR previews and exports, including existing library originals whose older proxies predate color conversion. Rights-approved backing tracks are loudness-normalized before mixing, and the Subtle and Present levels use restrained speech ducking so an enabled track remains audible beneath continuous dialogue. A ready edit can be re-rendered with the latest local processing while preserving the exact approved plan and consuming zero additional model tokens.

The editor receives a story spine plus the strongest retrieved source moments. A deterministic story check compares source-backed hook, payoff, reaction, and ending candidates; reports missing story roles; counts clean speech edits; and identifies repeated ideas so the model can choose one strong version. Edit-plan schema 1.2 requires every new clip to declare a narrative role and concise editorial intent. The planning instructions now favor a supported hook, minimal context, development, payoff, and requested ending while preserving complete speech and source truth. The review screen displays the local story check and timeline decisions in plain language. Legacy 1.0 and 1.1 plans remain valid, and deterministic local-only recipes populate the same metadata.

Acceptance helper after deployment: `python3 scripts/verify-phase13.py` waits for the local backfill, round-trips explicit story direction, attaches an existing library video without copying it, requires timestamped engagement evidence, edit guidance, selection reasons, and story coverage, archives its verification job, and records zero additional model tokens.

Next quality work: add local motion, shot-scale, face-presence, laughter/applause, and finer audio-energy signals to moment cards; then use those facts for cut-on-action, reaction cutaways, audio bridges, and visual hook alternatives.

Exit check for this checkpoint: deploy migration 019, pass the Phase 13 helper and full live suite, then make one real edit using all four story-direction fields and confirm the review timeline explains the hook, development, payoff, and ending.

## Phase 14 — local learning loop

**Purpose:** let repeated real-world feedback improve future edit decisions without training a model, uploading private media, or adding another hosted request.

Current source checkpoint (2026-10-25): migration 020 stores one editable rating against the exact edit-run version it evaluates. The review screen now asks for a 1–5 result, whether the edit is usable, optional notes, and bounded strengths or problems covering hook, story, pacing, captions, audio, visuals, colour, and ending. Saving is always explicit; opening or changing a control never starts a render or submits feedback.

The local aggregator learns separately for talking-head edits and montages. It waits for at least three rated examples, requires a repeated signal across at least 34% of that recipe's samples with a minimum of two occurrences, and suppresses tied conflicting advice. Every resulting directive records its tag, dimension, evidence count, sample size, and confidence. Verification projects are excluded. The owner can increase the minimum sample threshold or pause application from `/learning` without removing history.

Mature directives enter the next job's editor context as local preference evidence. The planning prompt may apply them only when compatible with the current brief and source evidence; explicit job instructions and source-only validation retain priority. Aggregation itself makes zero hosted model calls. The Learning dashboard also reports average rating, usable-edit count, delivered jobs, first-pass approval rate, recent teaching examples, and the evidence behind every active preference.

Acceptance helper after deployment: `python3 scripts/verify-phase14.py` temporarily records feedback against a finished real edit, verifies its dashboard and future editor context, requires the three-sample safety floor and zero added model calls, then restores the prior feedback or removes the temporary record.

Exit check: deploy migration 020, pass the Phase 14 helper and full live suite, rate at least three real edits of one recipe, confirm an explainable preference becomes active on `/learning`, and verify the next editor context contains that directive with its sample count and confidence.

## Phase 15 — deterministic pacing and social-safe captions

**Purpose:** let a reviewer correct pacing and subtitle presentation without risking a strong story or paying for another planning request.

Current source checkpoint (2026-10-25): migration 021 persists caption layout choices on each edit version. Vertical captions now default to a lower safe zone that stays above Instagram and TikTok controls, with upper and centre alternatives. Reviewers can shift all cues slightly earlier or later when source timing needs correction. These changes reuse the frozen edit plan, retain prior text corrections, and render locally with zero model tokens.

The editorial timeline measures pauses from local word timestamps. Clips containing a pause of at least 0.65 seconds expose explicit tight, short-comic, and long-comic beat controls. Applying one splits only the selected source range at word-safe boundaries, caps excessive silence at the chosen length, preserves the surrounding story, and creates a deterministic preview without asking the agent to reinterpret the request.

Exit check: deploy migration 021, tighten one measured pause, change a vertical edit to the lower app-safe caption position, confirm both previews retain the same surrounding clips and existing caption corrections, and pass the full live suite.

## Phase 16 — rights-aware music and creative effects

**Purpose:** add production polish with licensed music, sound effects, stickers, GIFs, and meme images while keeping the editor controllable and commercially safe.

Current source checkpoint (2026-10-25): migration 022 adds a licensed creative-asset catalogue, exact per-job music selection, bounded effect levels, and deterministic effect removal. The owner-facing **Creative** workspace imports files downloaded from a legitimate source such as Pixabay and records the creator, licence name, source page, proof note, attribution, allowed platforms, SHA-256, and commercial-use confirmation. Files remain local; archiving is reversible.

Edit plans now carry source-backed effect cues with an approved asset ID, timeline position, duration, screen position, intensity, and editorial purpose. Subtle, Social, and Meme-heavy modes permit at most 2, 4, and 8 cues. Validation rejects unknown assets, cues outside the edit, mismatched purposes, crowded timing, and strong cues in Subtle mode. FFmpeg mixes audio cues through bounded gain and a limiter, overlays reviewed visual assets, and records every cue plus its licence in the preview and delivery manifests. Reviewers can remove all cues and re-render the exact edit locally with zero AI tokens. The learning loop records whether effects landed, felt excessive, were too loud or mistimed, and whether a meme felt natural or forced.

Pixabay integration is deliberately file-based for this checkpoint: download a chosen asset from its official page, then import it with that page URL. This avoids scraping or treating search results as proof of rights. A provider API can replace the manual download later without changing the catalogue, planning, rendering, or review contracts.

Exit check: deploy migration 022, import one licensed music track and one licensed effect through `/creative`, create a Social-effects job, confirm every rendered cue appears in the manifest, remove the cues with the local review control, then run `python3 scripts/verify-phase16.py` and the full live suite.

### Revision and story-context hardening

Migration 023 persists a targeted or story-rebuild revision scope. The revision form distinguishes requests to adjust the existing cut from requests to reconsider all footage against the original brief. Rebuilding unlocks clip order and spoken selections while retaining other user protections. A new preview reports actual source, framing, audio, caption, and effect changes; descriptive prose changes alone do not count as an edit. If the editor returns the same executable plan, the review explicitly reports that result without automatically spending more tokens.

The editor now retains complete source transcripts alongside local moment cards when they fit within the existing context cap. Larger contexts distribute transcript evidence across files and across each file's beginning, middle, and ending, with explicit truncation markers. Model instructions emphasize complete thoughts, connecting setup, and cause and effect. Source tests cover context coverage and no-op detection; live acceptance is one explicitly submitted story-rebuild request and inspection of its measured revision report.

Multi-source hardening (2026-10-26): rich moment scoring metadata is compacted before dialogue is sampled. The same ranked spoken-hint allowance applies to each source; visual evidence and complete transcripts take priority over repeated score breakdowns. Byte-identical uploads remain valid selectable assets but are labelled as duplicates for planning. The reported 19-file inventory now fits the unchanged 120,000-character cap with every transcript passage retained. Original server context, word timestamps, and render validation remain intact.

For multiple distinct sources, the existing planning request now explicitly compares their subjects and endings, looks for complementary beats around a supported shared theme, and explains the chosen connection and omitted source groups in its editorial summary. It must keep product-specific claims and referents separate, obey a focused brief, and avoid forcing unrelated footage into the story. This does not add a model call or guarantee that every supplied recording belongs in the finished cut. Deploy, retry a context-limit failure, and use **Rebuild story** on an existing narrow edit to test the new planning behaviour; an exact re-render retains the old selection.

### Curated starter catalogue

The repeatable `scripts/import-creative-starter-library.py` importer installs 16 Kenney CC0 sound effects, 20 Google Noto Emoji v2.047 PNGs under Apache-2.0, and two CC0 background tracks from their original OpenGameArt submissions. It checks both whole-download and selected-member hashes, uses only the reviewed file URLs, reads named archive members without extraction, skips exact duplicates, and keeps each source URL, author, purpose, tags, licence, and notice in the local catalogue. The API image includes FFprobe to validate imports. Creative upload forms retain their form element before asynchronous work so a completed upload can reset cleanly. Delivery packages carry third-party credits and the full Apache licence for Noto artwork.

### Story-first duration and explicit pause evidence

Target length is now an approximate aim with the existing upper duration limit; a complete shorter story is accepted rather than rejected for missing a minimum duration. This applies to talking-head and montage plans and to local pause corrections. New editor contexts expose up to 24 source-timed word gaps of at least 0.65 seconds, with a warning that absent speech may contain laughter or meaningful actions. Planning guidance favors complete thoughts over filling time and asks for short natural pauses and bounded comic beats. Existing review controls can tighten a measured pause without a new AI request.
