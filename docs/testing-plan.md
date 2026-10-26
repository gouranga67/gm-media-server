# GM Studio testing phase

Updated: 2026-10-24 (Australia/Brisbane)

The testing phase is layered so a cheap failure is found before a GPU render or hosted editor request is started. A failed lane stops promotion, but the runner continues its remaining checks so one run produces a useful defect list.

## Gate 1 — source and build

Run as the normal `gm` user:

```bash
cd gm-media-server
./scripts/verify-source-suite.sh
```

This validates Compose, Python syntax, public-release safety, both TypeScript surfaces, the production Next.js build, and patch integrity. It does not touch production data, call a model, or render media.

### Editing input cost regression — 2026-10-26

The provider-context checks preserve every transcript segment, all retained story cards, editorial scores and cut guidance, revision locks, and learned instructions. Only duplicate scores/parent identities, transport bookkeeping, and server-side licensing metadata are omitted from the model input. Full rights records remain available to validation and rendering. Enabled effects retain the entire compatible inventory; an explicitly selected music track takes precedence over alternatives. JSON is serialized without formatting whitespace. The editor model, reasoning settings, source images, renderer, and context ceiling are unchanged.

Comparing identical captured live contexts with the previous implementation reduced text prompt size from 77,755 to 59,496 characters for the latest three-source job and from 77,700 to 59,445 for the highly rated three-source job (23.5% in both cases). These are character measurements, not billed-token estimates or evidence of equivalent model output. Confirm actual token usage and editorial quality on the next fresh job after deployment.

A worker regression also checks that a newly generated energetic talking-head plan missing its required transition receives one bounded transition at an existing clip boundary and renders after one planner call. Its source ranges, order, duration, framing, and audio selections remain unchanged. Saved plans and deterministic revisions do not opt into this completion step; existing transitions and single-clip plans are preserved. Genuine story failures still reach the AI repair path.

## Gate 2 — deploy and live core

Local rendered-quality inspection (Phase 17A) is report-only. Every new talking-head or montage preview and final export includes a versioned `quality_review` in its manifest; final ZIPs include the same report. Inspection runs locally with a 30-second FFmpeg budget plus a bounded probe, reports zero model usage, and preserves the video and edit plan even if inspection fails. Word-timing gaps and dark/quiet intervals are suggestions to review, not instructions to remove reactions or humour. Caption checks inspect the schedule, not OCR of burned-in text. Colour checks inspect metadata, not skin-tone accuracy. Story judgement remains explicitly unassessed.

After deployment, create a fresh preview or re-render an existing exact edit, then run `python3 scripts/verify-phase17.py` (optionally `--job-id UUID`). This acceptance helper only reads the report and never generates an edit or incurs model usage. Older renders have no report until re-rendered. The core live suite does not require a new render just to make this optional acceptance check pass.

Source acceptance covered 184 backend/render tests, seven source/build checks, and static report rendering for legacy, complete, incomplete, and timestamped results. A local copy of a successful real preview completed all 11 review checks in approximately 0.9 seconds with no findings, no hosted model calls, and an unchanged video SHA-256. This demonstrates technical inspection, not autonomous story assessment; live report persistence still requires deploying and rendering with the new build.

Status: **Passed on 2026-10-24.** All 10 live core gates passed, including 61 backend tests. The deployed catalogue, exact-duplicate audit, local visual index, managed library, and complete job history were verified without deleting an original.

Deploy once, then run the live suite with Docker access:

```bash
cd gm-media-server
sudo ./scripts/install-service.sh
sudo ./scripts/verify-live-suite.sh
```

This checks service health, migrations 010–024, backend unit/integration tests inside the pinned CUDA worker image, an existing real analysis manifest, reusable-library references, exact-duplicate calculations, the content catalogue backfill/search API, local semantic visual indexing, reversible managed-library operations, complete non-destructive job-history classification, the Phase 11 editorial workspace, the Phase 12 product controls, the Phase 13 local story index, and the Phase 14 feedback-learning loop. The Phase 12 helper round-trips a temporary member, operational limits, and job archive state. It runs retention behind a 10-year threshold and requires `originals_removed: 0`. The Phase 13 helper waits for local moment-card backfill, attaches an existing source to a verification job, and proves exact source ranges, engagement scores, clean edit guidance, story coverage, and zero additional model calls. The Phase 14 helper temporarily records and restores version-specific feedback, verifies the three-sample safety floor and future editor context, and makes zero model requests. Backend regression tests also verify progressive word-timed caption cards, speech-boundary handles, deterministic removal of unrequested revision music, audible loudness-normalized backing music, HDR/HLG-to-BT.709 tone mapping, and explainable conflict-safe preference aggregation. The test location matters: it catches compatibility differences between the Python 3.13 API image and the CUDA image's Python runtime.

The migration gate checks the completed one-shot migration runner instead of opening a second raw database session. The runner exits successfully only after every bundled migration has applied, which avoids a diagnostic query waiting behind a transient PostgreSQL lock. A failed suite prints every failed gate by name at the end.

The library verifier uses one stable verification project and job on every run. The duplicate verifier may store a canonical preference, but neither helper deletes, moves, merges, or rewrites an original media file. The catalogue and visual-search tests are read-only after their background backfills; the visual test reads a generated source-frame derivative but never modifies an original.

Phase 9 storage acceptance is a separate explicit operation because it changes physical allocation while preserving every logical original path. After a current encrypted backup, run `python3 scripts/verify-phase9.py --confirm-storage-optimization`. It re-hashes a reviewed exact-copy group, atomically shares its disk blocks, verifies that all records remain, and confirms that the group has no unoptimized bytes left.

## Gate 3 — opt-in render and editor acceptance

### High impact finishing

Migration 024 enables the optional High impact editing style for jobs and saved profiles, and records picture-overlay removal revisions. Existing job defaults stay Energetic with effects Off. The new style targets a relevant visual or sound change around every 2–3 seconds using the existing planning request. A named rhythmic-punch preset changes framing every 2.5 seconds without dividing the speech timeline. Intentional holds/reaction shots retain their planned framing. Sound and sticker cues still obey the separately selected effect level and approved library.

Schema 1.4 adds up to eight picture-only B-roll overlays from the job's own uploaded/attached video and images. Each lasts 0.5–4 seconds, overlays cannot overlap or leave the timeline, and total coverage cannot exceed 60%. Their original audio never enters the mix. B-roll is composited below stickers and captions, with the same HDR conversion as the base footage. Overlay timings follow local reordering, pause tightening, and duration variants. Old plans remain readable; empty overlay fields are omitted when serializing older schema versions to preserve their existing document hashes.

After deploying, choose **High impact** for a fresh job, include relevant close-ups among the selected media, and choose Social or Meme-heavy effects if sounds/stickers are wanted. Review the picture changes and B-roll explanations in the edit breakdown. **Remove B-roll & render** produces a local revision with no model call; ordinary clip framing controls also offer the rhythmic preset. Run `python3 scripts/verify-high-impact.py` after a preview finishes for read-only plan/manifest acceptance. A lack of suitable uploaded B-roll may legitimately produce no cutaways.

Backend tests include real CPU-encoded video/image overlays with sound accents, verify that the picture switches at scheduled times, and compare decoded audio byte-for-byte against the same edit without B-roll for both recipes. Live NVENC, editorial relevance, and actual token usage still require a fresh job on the deployed build.

Source acceptance: 200 backend/render tests and seven source/build checks passed. Static React rendering verified the cadence count, B-roll explanation, local-removal button, and rhythmic framing option. Worker tests verify that finishing uses one planner call and that B-roll removal uses none; local-only jobs retain their fixed recipe.

### Standard delivery acceptance

Status: **Passed on 2026-10-24.** The complete live suite passed 13/13 gates. The deterministic preview rejected an invented asset and rendered with NVENC; the talking-head delivery validated its full-HD MP4, captions, cover, ZIP package, provenance, and phone download; and the montage validated source-speech captions, seven selectable account models, measured usage, vertical output, NVENC, and phone download.

Only after Gate 2 passes:

```bash
sudo ./scripts/verify-live-suite.sh --confirm-render-and-ai
```

This repeats the live core and then exercises deterministic preview rendering, a talking-head revision/final package, and the montage/caption/model/usage path. It can create edit-plan versions, use GPU time, and consume connected ChatGPT plan allowance. It never creates synthetic media.

The same lane runs `verify-phase10.py` against an existing delivered job. That check performs a local square render but makes no new editor-model request and verifies the recorded token total remains unchanged. This Phase 10 check passed on 2026-10-24: the profile round-trip, 1080 × 1080 render, ZIP download, and zero-token assertion all succeeded.

## Gate 4 — physical phone acceptance

From a phone connected to the tailnet:

1. Open GM Studio, search the server library for a filename and for a phrase spoken in a clip.
2. Confirm the phrase result shows the exact quote and source time range; select it and combine it with one new upload.
3. Create a talking-head reel, request a revision, approve it, and download the final package.
4. Create a montage with at least two videos/photos, captions, and one rights-approved music track; approve and download it.
5. Put the phone in airplane mode during a new upload, reconnect, and confirm the upload resumes without a duplicate original.
6. Open **AI usage** and confirm both jobs and their token totals appear; open **Duplicate audit** and confirm it reports copies without offering deletion.
7. Check portrait layout, scroll position after the phone picker closes, playback, and downloads in the ordinary browser and one private/incognito session.

Record the job IDs for both successful edits and any failure message exactly as displayed. A screenshot is useful, but the job ID is what ties the UI to server logs and provenance.

## Gate 5 — recovery and soak

The destructive/restart drills belong at the start of Phase 7, after backup work begins:

- reboot during a queued or active render and confirm durable recovery;
- repeat the worker-kill analysis recovery drill;
- check disk, GPU temperature, queue depth, failed jobs, SMART health, and backup age;
- restore a deliberately deleted test project from an encrypted backup.

No original-media deletion test should run before the backup and restore path exists.

Install and exercise the local recovery layer:

```bash
sudo ./scripts/install-backup-service.sh
sudo ./scripts/show-backup-recovery-key.sh
sudo ./scripts/verify-backup-restore.sh
```

Save the displayed recovery key in a password manager; never paste it into chat, email, logs, or a repository. The restore helper writes only to a newly created `/tmp/gm-media-restore.*` directory and removes it after validating the dump and recovered originals.

If a recovery key is ever pasted or otherwise exposed, rotate it immediately:

```bash
sudo ./scripts/rotate-backup-recovery-key.sh
```

The rotation shares the backup/restore host lock, validates the replacement before installing it, revokes the exposed key, and verifies that the old password no longer opens the repository. After it passes, run `show-backup-recovery-key.sh` and save the replacement directly in a password manager without copying it into chat or logs.

Complete the private boundary once from the Lenovo. This discovers the server's current Tailscale owner and DNS name, writes them to the protected deployment environment, rebuilds the web layer, and proves that direct unauthenticated access is rejected while Tailscale Serve remains tailnet-only:

```bash
sudo ./scripts/configure-private-access.sh
```

Create the OneDrive connection on a Windows computer with `scripts/onedrive-enroll-windows.ps1`, securely copy the resulting `gm-studio-rclone.conf` to `/tmp/gm-studio-rclone.conf`, then import it on the Lenovo:

```bash
sudo ./scripts/import-onedrive-backup.sh
```

The importer removes the transferred token file after validation, installs the daily timer, uploads only the already-encrypted Restic repository, verifies the remote file set, and retains 90 days of displaced remote objects for recovery from a bad sync.

Finally, with no real edit running, start the deliberate full-machine recovery drill:

```bash
sudo ./scripts/start-reboot-recovery-drill.sh --confirm-reboot
```

The SSH session will disconnect. After the Lenovo returns, reconnect and read the machine-recorded result:

```bash
./scripts/show-reboot-recovery-drill.sh
```

The drill reuses a completed verification edit plan, consumes no additional model request, interrupts it during rendering, checks that the boot ID changed, waits for the durable worker recovery path, and requires a non-empty recovered preview.

Revision regression coverage: complete dialogue remains available alongside moment cards; bounded contexts retain source endings across all files; story rebuild mode reaches the editor with explicit scope; revision reports compare actual cut and render choices rather than prose changes. Migration 023 persists the requested revision scope.

Multi-source regression coverage: a metadata-heavy 19-recording inventory fits the existing context cap without removing any transcript passage, source identity, production-chatter warning, or visual card. Duplicate checksums label repeated uploads without deleting files or merging asset IDs. Both recipes receive cross-source story guidance in their existing planning request. Private captured contexts can be checked locally, but must not be committed as test fixtures. Live acceptance: retry the previously blocked selection after deployment; then create or rebuild a story from related recordings and compare its chosen sources, connecting idea, product referents, and omission rationale. A technically valid plan is not proof of a coherent story; watch and rate the actual result.

Mixed-source upload regression coverage: `npm run test:media-selection` mounts the real form components in a DOM runtime with fake HTTP and upload transport. It checks combined server/device selection into one job, explicit preview submission, standalone library imports with `job_id=null`, upload-group naming and reuse, pause/resume, analysis status retries without repeated uploads, and rejection of invalid or empty files before network mutations. It is included in the source suite. Live acceptance after deployment: upload a small product close-up from `/library`, wait for **Ready in your library**, then create a High impact job combining existing server footage and another newly selected device file. Confirm all chosen sources reach the job and that editing starts only on explicit submission. This interaction suite does not verify real network transfer speed or rendering quality.
