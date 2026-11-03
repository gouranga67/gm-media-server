# GM Studio testing phase

Updated: 2026-11-02 (Australia/Brisbane)

The testing phase is layered so a cheap failure is found before a GPU render or hosted editor request is started. A failed lane stops promotion, but the runner continues its remaining checks so one run produces a useful defect list.

## Combined deployment checkpoint — 2026-11-02

Build `84b96419` is deployed. The [combined acceptance report](phase-reports/combined-acceptance-2026-11-02.md) records 536 passing backend/local-render tests without skips, eight source gates, eight read-only live verifiers, 27 desktop/phone browser page views and one isolated zero-AI NVENC render. Revision typing produced no write request. These results establish technical readiness, not creative quality or completion of every acceptance lane.

The next server-terminal action is `sudo ./scripts/verify-live-suite.sh`, which needs interactive Docker/sudo access. Physical-phone playback, real-footage story/revision/blooper review, independent lesson trials, recovery and actual Meta posting remain separate. Phase 14 readiness is now read-only; Phase 5 renders only in its own local-only verification job. The core runner mounts host scripts read-only for their isolation regressions. No additional application rebuild is needed for these host test-helper changes alone.

## Reliability and efficiency sprint acceptance (migration 039)

Source verification passed 478 backend tests with real CPU FFmpeg and no skips, 46 browser interaction tests, TypeScript, production build, public-release audit and Compose validation. An isolated PostgreSQL engine applied all 39 migrations and exercised actual queue SQL: existing grids survive, new imports are claimed, failures back off, interrupted work is reclaimed, obsolete claim completion is rejected and final attempts stop retrying. Temporary test dependencies were unpacked outside the repository; no system packages or live container state were changed.

The off-site tests run the actual shell pipeline and JSON writer against a fake transport. They cover transfer/comparison failure, missing history, retention-only warnings and preservation of the previous match timestamp. With rclone installed (or `GM_TEST_RCLONE` set to its executable path), an additional disposable local transport test proves that a newly displaced object with an old modification time survives, recent history buckets remain, old eligible history files are deleted and current repository files are retained. This never contacts OneDrive. These checks do not establish remote availability or a successful restore.

After deployment:

1. Run the core live suite. Its migration check must report `039_background_music_analysis.sql` from the database, not merely a migration container with exit code zero.
2. Import one new rights-recorded music track after the worker is already running. Allow an idle turn; `music-tracks` should report beat analysis moving from pending to ready without a restart. Tracks with failed optional analysis remain otherwise eligible, and repeat failures must stop after three attempts.
3. Run the existing off-site service and refresh System health. Upload, file-size comparison and history maintenance should report separately. Investigate `attention` warnings even when the copy matched; use the separately documented restore drill to establish recoverability.
4. Make an ordinary music-enabled edit and check story, words, music selection, timing, captions and colour against a known good result. The compact music context retained all 24 choices and full render data, but subjective edit quality and total token savings require this real-footage comparison.
5. After processing a task, redeploy once and confirm recent timing samples remain. Samples are bounded to 240 and exclude queue wait, billing and failed-task durations from successful-task percentiles.

The learning loop, new story-selection behaviour and natural-language revision routing are not changed by this sprint. Do not treat passing technical checks as acceptance of those later phases.

For real-footage testing of the deployed features, use the [hands-on user checklist](user-acceptance-checklist.md). It starts with eight priority checks, then covers source selection, bloopers, library management, precise edits, finishing, phone delivery, learning and appliance behaviour. The [brief-first editing plan](brief-led-editing-plan.md) records the implemented migration-033 increment and later assembly work.

## System audit baseline and proposed regression coverage

The [2026-10-26 system audit](system-audit-and-roadmap.md) inspected 18 page route files and navigated 17 live screens at desktop and phone widths (34 navigations). Each returned HTTP 200 without observed HTTP failures, uncaught page errors or root horizontal overflow. Photos and B-roll filters responded. All non-GET/HEAD requests were blocked; these results do not establish upload, render, save, role-change or recovery acceptance. No hosted model request was submitted. Automated accessibility checks flagged unnamed Creative buttons, unlabelled Brand selectors, Library row-name mismatches and contrast defects on four other screens.

Before promoting proposed phases 19–25, add:

- Browser tasks for shared selection, recoverable drafts, keyboard/focus behavior, partial analysis, stale proposals, scoped revisions and idempotent error recovery, plus physical-phone playback/upload checks.
- Real PostgreSQL migration/query integration checks alongside mocks, including creative music compatibility and the shared metadata contract.
- Mixed ingest/search/render scheduling tests, bounded frame extraction, versioned analysis reuse, measured stage latency and peak GPU memory on the 4 GB card.
- A private representative story-quality set with paired human review; retain excellent existing edits as a baseline and keep a held-out portion.
- Render fixtures for source attribution, word joins, caption fit/sync, audio balance, HDR/color, transitions and future alpha/mask composition.
- Scoped learning-rule evaluation and rollback; optional AI critique must be budgeted and cannot be the sole promotion authority.

These are planned checks. The read-only audit did not rerun mutating live verifiers or certify new output quality.

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

This checks service health, migrations 010–024, backend unit/integration tests inside the pinned CUDA worker image, an existing real analysis manifest, reusable-library references, exact-duplicate calculations, the content catalogue backfill/search API, local semantic visual indexing, reversible managed-library operations, complete non-destructive job-history classification, the Phase 11 editorial workspace, the Phase 12 product controls, the Phase 13 local story index, and the Phase 14 feedback-learning loop. The Phase 12 helper round-trips a temporary member, operational limits, and job archive state. It runs retention behind a 10-year threshold and requires `originals_removed: 0`. The Phase 13 helper waits for local moment-card backfill, attaches an existing source to a verification job, and proves exact source ranges, engagement scores, clean edit guidance, story coverage, and zero additional model calls. The Phase 14 helper now reads learning readiness, verifies the three-sample safety floor and future editor context, and makes zero feedback writes or model requests. Deliberate feedback saves are covered separately; it never temporarily replaces a real teaching example. Backend regression tests also verify progressive word-timed caption cards, speech-boundary handles, deterministic removal of unrequested revision music, audible loudness-normalized backing music, HDR/HLG-to-BT.709 tone mapping, and explainable conflict-safe preference aggregation. The test location matters: it catches compatibility differences between the Python 3.13 API image and the CUDA image's Python runtime.

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

B-roll selection follow-up (2026-10-26): High impact hybrid jobs now pack derived source thumbnails into labelled sheets within the existing four-image talking-head or twelve-image montage budget. Up to six sources fit each sheet; unpictured coverage is explicit. This makes later-attached product clips and stills visible instead of limiting evidence to the earliest recordings. Tests cover a 19-source selection, missing early derivatives, bounded larger inventories, and text-only privacy. Thumbnails identify source content, but do not verify every frame, facial motion, or unreadable review text.

New hosted plans receive local word-timed B-roll guidance. A conservative guard removes video overlays that overlap recorded speech with a 150 ms margin, retains other valid overlays, and records removals in the finishing manifest without changing the main dialogue timeline or asking the model again. Wordless gaps remain usable; segments supply conservative fallback timing when words are unavailable. Unknown source IDs remain subject to normal ownership validation. Existing frozen plans are retained: use **Remove B-roll & render** for a local correction, or explicitly submit a targeted revision to choose new supporting pictures. Replay evidence caught the reported speaking cutaway, retained the original base clips, and pictured all 19 sources in four sheets without a hosted request.

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

Library organization regression coverage (migration 025): the DOM suite also mounts the full media browser, exercises footage views, speech/scene search, batch and single rename, explicit Trash confirmation, restore, failed-batch selection retention, upload prefix/role assignment, and New job role filters with selection persistence. Backend tests check atomic stale-selection rejection, mixed-media role validation, preservation of names/notes/favorites/job references, schema limits, and role retention in compact planner context. After deployment, run `python3 scripts/verify-phase8.py` for real SQL-backed metadata, role, renamed-picker search, collection filtering, batch failure, Trash/restore, and provenance checks. This verifier temporarily renames one original and restores its metadata; it deletes no originals and makes no AI calls.

Still-image B-roll regression coverage: real FFmpeg renders use wide, tall, and transparent PNG fixtures with distinct markers on all four source edges. Checks verify every edge remains visible, transparent regions reveal the dimmed footage, captions remain visible, the source picture returns outside the cue interval, and decoded speech audio matches the baseline byte for byte. Layout bounds are checked at preview, Full HD vertical, square, and landscape sizes, including alternate caption positions. The existing talking-head and montage overlay integration checks still run. Live acceptance: deploy, choose **Re-render exact edit** on an existing cropped-review job, inspect both cards for complete text/stars and readable caption spacing, and run `python3 scripts/verify-high-impact.py --job-id JOB_ID` to inspect the framing manifest without an AI request.

Library concept desk (migration 026): backend checks cover source deduplication, fair bounded coverage of early/late speech, source-only script citations, unsupported/repeated source rejection, privacy-dependent picture sharing, request ID reuse, atomic two-concept selection, stale/trashed source refusal, capacity rollback, and usage recording before invalid-proposal failure without automatic paid retries. DOM checks exercise explicit generation, recorded script/picture inspection, selecting at most two options, rendering only the chosen IDs, loading saved sessions without generation, and retaining selection after an error. `verify-library-concepts.py` is a read-only live-suite lane; it checks readiness and persisted result contracts and never makes a model request or creates a job. A human must run one real concept generation and review the selected rendered previews after deployment to establish semantic and production acceptance.

Blooper concepts (migration 027): local tests check self-correction/restart/laughter/stammer clues, weak repeated-take evidence, same-source context and gap boundaries, invalid-time rejection, false positives on ordinary claims, input immutability, source-backed scripts, optional empty results, candidate-anchor validation, mode-sensitive request reuse, bounded inventory and the explicit outtake editor instruction. DOM tests select Bloopers, show candidate reasons and source links, require an explicit preview action, and reopen an empty saved result without creating jobs or making another model call. After deployment run `python3 scripts/verify-library-concepts.py`, then choose Bloopers on `/concepts`, scope to known outtakes, inspect the proposed source passages and watch a selected preview. Check that the mistake and real recovery remain, long empty gaps are removed, and a subsequent normal story edit still favors clean takes. Automated model responses are mocked; these tests do not establish real-world detection recall or comedy quality.

Photo categories and auto-sort (migration 028): backend tests check mixed-media categories, metadata compatibility, complete/unique source coverage, preservation of manual names and labels, speaking-take protection, privacy, one model request per worker task, usage persistence on invalid proposals, explicit application, no-op repeated application, and rejection of stale/trashed/unknown selections. DOM tests categorize/filter a photo, edit suggested names before applying, reopen saved suggestions without regeneration, and retain review selection on application failure. Isolated PostgreSQL tests run the actual application SQL and migration chain against synthetic records, including music JSONB compatibility, usage constraints and tag/notes/favorite preservation. The live verifiers exercise read-only auto-sort contracts and the actual concept music lookup. Human acceptance: deploy, retry the saved blooper concept with Subtle music without generating fresh ideas, review/download it, then auto-sort a mixed batch of known talking footage, product cutaways and review images and inspect the names/categories before application. No automated test claims to establish live model labeling accuracy.


Brief-first assembly (migration 033): local routing tests cover mixed speech/pictures, visual montages, negative instructions, bloopers, profile pacing, unsupported inputs, immutable preflight, once-only persistence, stale override refusal, request ID replay and worker resolution before one editor request. DOM tests cover visible brief shortcuts, automatic defaults, explicit Apply/Start actions, source-first ordering and profiles that preserve purpose/assembly. An isolated PostgreSQL check runs all 33 migrations and actual application inserts/updates against synthetic records, verifying that legacy engines, styles and frozen plan documents remain unchanged. Real FFmpeg regression renders remain part of the backend suite. The new `verify-brief-first.py` live lane only inspects deployed contracts and at most five existing job interpretations; it creates no jobs or model requests. Human playback for R1–R8 is still required to assess editorial quality.


Blooper incident focus: discovery now reuses stored ASR word timings only for recordings containing specific incident clues. It offers short clause-bounded mistake/reaction windows and short adjacent recovery rather than whole catalogue chunks. Long passages with missing, partial, invalid or mismatched word timing are left for manual review; no timestamp interpolation or extra transcription/classifier call is used. First plans from newly generated focused concepts must retain the incident and remain inside selected source windows, with short speech handles. Existing saved concepts and approved plans are retained, and explicit later revisions remain possible. Regression tests cover unrelated pitch removal, short recovery, cross-source isolation, incomplete timing, original-text preservation, legacy scope compatibility, plan bounds and omitted-incident refusal. A private offline comparison against the reported failure reduced the offered material from a whole 27-second pitch to roughly nine seconds around the incident; this is a source-window check, not proof of comic quality. Generate fresh concepts after deploying, then review the actual raw moment and rendered gag.

Draft resume: reopening a job with no editing run must say it has not started, inspect source readiness, and require Start editing. It must never claim the server is already planning or silently queue a paid request. The DOM suite checks this route and explicit one-time start.

Preview progress: queued, planning and rendering runs show their actual stage, elapsed waiting/run time, last successful status fetch and (for active workers) the persisted lease heartbeat. Heartbeats indicate worker contact, not rendered-frame progress. An active run without a heartbeat for two minutes shows an uncertainty notice; a failed status fetch shows a separate reconnecting notice. Loading the review does not claim planning. No completion percentage, queue position or ETA is invented, and observing progress never submits a model request. DOM checks cover each stage, stale heartbeat and disconnected polling; inspect phone and desktop layouts before deployment.

Revision execution fixes — 2026-10-27 (Australia/Brisbane): two live version comparisons showed a dialogue cleanup changing 48.48 seconds to 48.08 seconds and a volume request replacing the closing take. Speech plans now expose bounded per-clip source gain to the hosted planner, direct agent submission and local precise-edit path, matching the existing montage capability. Both preview and final rendering apply it before concatenation/whole-reel normalization; independent audio joins retain the same gain. Default zero gain keeps old serialized speech plans and filter chains unchanged. Revision prompts direct volume-only changes to preserve the take and dialogue; reports show exact source ranges and gain changes rather than only counting changed clips. Protective word handles can fill nearby silence but cannot add a neighbouring omitted word back. An offline replay of the reported opening now retains the requested 8.85-second end instead of expanding to 9.01 seconds and reintroducing “So.” No historical job or plan is rewritten and no automatic model retry is added.

Validation: 358 backend tests passed, including actual FFmpeg rendering that measures a selected quiet passage before/after a 12 dB boost relative to the unchanged first passage. Agent tool TypeScript, Python compilation, public-release audit and patch integrity passed. This proves execution and timing behaviour; it does not establish that a hosted revision will choose every desired correction or that the user's actual recording is perceptually balanced. After deployment submit an explicit targeted revision on a chosen version, compare the recorded changes and listen to the affected passage. For filler removal, identify the phrase or reel time and verify that a meaningful connecting word was not removed.

## Story consistency pass — 2026-10-27

New ordinary concept discovery reads existing word-timed transcript derivatives, without re-transcribing footage. Verified matching word timings can split sentences and exclude a punctuated disposable prefix. Close unfinished continuations from the same recording join into one selectable passage, with catalogue provenance retained; missing/mismatched word timings preserve the original passage and expose uncertainty. No timestamp is interpolated. Derived passage IDs are deterministic negative 52-bit integers, compatible with browser JSON numbers. The existing 60-source and 36,000-character discovery bounds and image limits remain. The producer uses its existing angle field to state the central point and explain the recorded ending; no new planning request is introduced.

Fresh story concepts retain a versioned selection contract. The first generated plan checks the selected source speech, passage coverage and narrative order, including protected negations, numbers and boundary words. Unexpected additional spoken claims and missing/reordered selected beats use the existing single bounded repair opportunity. This verifies source selection and structure, not causal meaning or viewer engagement. Legacy saved concepts, exact re-renders and later explicit revisions do not acquire a new hard constraint. Bloopers retain their separate incident policy. Do not automatically migrate a saved concept into this contract: generate fresh ideas after deployment to test the full flow.

New ordinary speech stories also receive one conservative local finishing pass. It can remove a standalone disposable opening, shorten only long intervals supported by both word gaps and measured quiet audio, and raise unusually quiet selected speech with a maximum 6 dB boost and measured peak headroom. Whole-file loudness alone cannot trigger it. Analysis covers at most six passages of at most 12 seconds each within a shared eight-second subprocess budget; coverage and unavailable measurements are reported. Calm pacing, explicitly preserved pauses, intentional reaction/hold timing, existing local finishing, explicit source gain and requested quiet delivery are respected. Timed effects, B-roll and finishing anchors follow timeline changes. A failed optional inspection or invalid cleanup preserves the validated plan. Existing promotional cleanup is unchanged; this increment extends conservative finishing to ordinary stories.

Preview manifests retain story-contract checks and actual local cleanup changes. Approved final exports carry those reports forward, without running cleanup again. The review screen exposes them under Local quality review → Story selection and cleanup, with human story judgement explicitly required. No additional routine hosted model call, transcription, external asset upload, migration or new user approval step is involved.

Acceptance covers sentence splitting/joining, missing timing, stable citation IDs, source isolation, discovery coverage budgets, selected ending/order/claim checks, negation protection, bounded worker repair, safe pause and level changes, reaction/quiet-direction preservation, time-budget enforcement and legacy compatibility. Actual FFmpeg fixtures measure quiet speech and render a seven-second setup/silence/result sequence as approximately 3.6 seconds while preserving both voiced windows. Offline replay of stored cream footage joins the winter dry-skin condition with its recorded recommendation. Human playback remains necessary to assess whether fresh concepts and edits are stronger; no new live model request was used for development verification.

Auto-sort filename regression — 2026-10-27: older metadata saves or applied suggestions can store the original camera filename as `display_name`. Auto-sort previously interpreted every nonempty saved name as custom and restored the filename after the model suggested a descriptive name. The preservation guard now distinguishes a copy of the original filename (ignoring whitespace/case) from a descriptive custom name, including old saved inventory snapshots. The model receives the same distinction. Filename placeholders also cannot count as descriptive evidence for unseen media. Actual descriptive names, manually chosen roles/categories, explicit review/application and original media remain protected. Regression tests cover a transcribed older clip, preserved descriptive names and an unseen image with only a stored filename. No migration, re-upload, colour processing, automatic rename or extra model request is required. After deployment select the affected files and request fresh suggestions; previously saved suggestions retain their original names until explicitly edited or regenerated.

Meta publishing increment — 2026-10-27: migration 034 adds encrypted social connections, one-time owner-bound OAuth states, immutable export/caption posting drafts, per-account durable publishing records and separately opted-in caption requests. Instagram and Facebook use direct binary uploads of an approved full-quality export. The worker persists each remote stage, separates processing from publication, and stops ambiguous writes for reconciliation. A publish-start timestamp distinguishes an interrupted upload from a potentially completed publish; neither a failed HTTP response nor a worker restart blindly replays publication. Owner attestation can resolve an otherwise uncheckable unknown attempt as unpublished, with an audit event. Queued/scheduled/processing/uncertain posts pin the export against retention. Caption generation reads the approved VTT rather than omitted source transcript chunks, makes one bounded request, records tokens, and never changes or publishes the draft automatically. The usage dashboard identifies these requests separately.

Verification includes simulated OAuth/account discovery, replayed/expired state rejection, encrypted-token and sanitized-error checks, upload host validation, stream upload protocol, version/hash/caption guards, permission/expiry checks, repeated approval and interrupted-write recovery, selected-caption UI interactions, explicit publication, callback StrictMode idempotence and legacy rendering regressions. An isolated PostgreSQL engine executes all 34 migrations and actual new draft/approval/worker SQL, including unique constraints, caption-usage checks and retention pins. No real Meta app/account connection, media upload or social post is created during automated verification. The remaining acceptance boundary is the user's configured Meta app: connect accounts and explicitly approve one real test post on each platform. See [Meta publishing setup](meta-publishing-setup.md).

Creative alternatives (migration 035): backend checks cover request replay/conflicts, reference preservation, local-only refusal, bounded history, explicit concept-script unlocking, equivalent-source aliasing, source interval unions, tiny trims, split clips, reordered cuts, another take of identical speech and substantive treatment changes. A simulated worker returns a similar valid plan once and proves that no novelty request is automatically added. DOM checks cover explicit choice/submission, retained direction/error/request ID, earlier-version playback during processing, honest similarity reporting and explicit local restoration. Isolated PostgreSQL runs all 35 migrations and the actual alternative insert/replay/history queries, verifies nonce uniqueness, and checks the original plan/approval/export remain intact. No real model calls are made in these checks. Live creative acceptance requires the paired footage tests in the hands-on checklist; source overlap cannot establish story quality.

Adaptive duration (migration 036): regression coverage reproduces the 60.6-second failure in both engines, checks flexible/default/strict/absolute limits, and verifies source ranges remain unchanged when a flexible plan already fits. Local repair tests preserve complete word intervals and retime surviving B-roll, reject noise or missing word timing, respect intentional pauses/outtakes and recover safely from measurement timeout. Real FFmpeg distinguishes a quiet gap from a tone. Duration-only conflicts record usage once and do not request a second hosted plan. Transcript preflight merges overlaps and identical uploads without claiming to measure required speech.

## Camera timing and silent cutaway safeguards — 2026-10-28

The Shed life 1 investigation found a 60 fps talking clip entering `zoompan(d=1, fps=30)` before frame-rate conversion. The picture advanced at half speed while audio advanced normally; final padding/trimming concealed the fault from duration-only QA. Both engines now convert source timestamps to the output cadence before video camera effects. Still-image expansion remains separate and establishes frame durations before padding, avoiding repeated timestamps from zero-duration zoom frames. The shared finishing manifest declares `video_timing_pipeline=source_timestamps_before_camera_effects_v1`; this identifies processing, not a measured lip-sync score.

Real FFmpeg regressions use colour changes and matching audio pulses. They check source time after a nonzero seek at 24, 25, 30, 50, 60 and 120 fps, fractional rates and variable frame rate across supported camera presets. Mixed-rate, two-clip previews and exports check picture progression, unchanged decoded audio, scheduled pulses, keyframe motion and unchanged plans in both engines. A still-image case checks exactly 60 frames for a two-second expansion. The worker rebuild regression preserves the saved clips, framing, cutaway and duration snapshot without planning, generated-plan cleanup or additional model usage. Local tests use CPU encoding; live NVENC playback remains an acceptance check.

For newly generated cutaways, missing ASR is explicitly unknown visual speaking status. Talking-labelled video without recognized speech needs a human-marked B-roll range covering the complete cue. Human Talking/Avoid ranges exclude cutaways, and B-roll annotations cannot override recognized speech. Unlabelled product/action footage remains eligible; there is no face detector or extra analysis request. Existing frozen edits are preserved on exact re-render.

Deploy, reopen **Shed life 1**, and choose **Re-render exact edit**. Check that the speaking shot after the soap-cutting cutaway advances naturally with the voice, including its punch-in. Confirm the original story and cutaway remain, then approve/export and inspect the final MP4 on a phone. This patch requires no migration, re-upload or new hosted plan.

UI checks verify new-job defaults, explicit duration save without model work or retry, and retained inputs on a failed save. Isolated PostgreSQL applies all 36 migrations and exercises actual job/revision/rebuild/settings/claim queries, old-job migration, per-run snapshot preservation and extended feedback bounds. Phone/desktop browser checks use synthetic HTTP fixtures; live deployment and required-point playback remain separate acceptance checks. See D1–D6 in the hands-on checklist.

## Creative toolkit expansion — 2026-10-31

The flow is Library → Music & effects → select files → review per-file titles/source links and shared licence → explicit import → local catalogue → bounded planner shortlist → validated treatment timing → preview/export. Selecting files or changing a field starts no upload, edit, model request or publication. Imports are sequential, duplicates are kept in place, failed/unfinished rows alone are retried, and stop takes effect after the current file. Imported music is never used when Music is Off.

Regression coverage checks streamed upload limits/cleanup, SQL placeholder/column agreement and guidance recording; all 37 migrations, pinned metadata backfill, actual import/update SQL and duplicate constraints are also exercised in isolated PostgreSQL. New render tests inspect picture changes and distinct voice/music frequencies in both engines at preview and export quality: callouts/pointers appear only in their intervals, a music pause suppresses the music tone while retaining the voice tone, and the plan remains unchanged. Treatment timings follow timeline changes; caption bands take priority; unsafe subtitle commands, nonfinite values, invalid windows and overlapping same-kind treatments are rejected. Legacy finishing serialization keeps its previous hash inputs.

Interaction checks cover explicit batch submission, source-link validation, duplicate skips, partial failures, retry counts and local callout submission with retained settings. Browser tests at 320, 390 and 1440 pixels use synthetic files and mocked HTTP, checking the real page, accessibility, console errors and overflow. Full-stack live imports used the existing owner API; no test jobs or hosted requests were created. New schema/migration/finishing controls still require deployment and a real-footage preview/export acceptance. CPU FFmpeg is exercised locally; NVENC remains a deployed check.

After deployment, check the live sound/graphic counts, search the collection and inspect the starter guidance. Start a fresh Social/Meme-heavy test with an evidence-backed reveal/reaction, then review its effect breakdown and final export. On a saved test reel use Finishing tools to add a short callout, fixed pointer or music pause; changing fields must do nothing until Create preview is pressed. A repeat exact render preserves the saved treatment choices. Humour and automatic editorial relevance are human acceptance checks, not claims made by the automated suite.

Implementation validation: 453 backend tests and 45 DOM interaction tests passed, along with the 37-migration isolated SQL check, browser checks, web/agent TypeScript, production web build and public-release audit. Regression tests confirm that cosmetic treatments do not disable existing story cleanup or safe duration repair.

## Approved AI-labelled music — 2026-10-31

Check migration 038 in an isolated database with existing music plus approved AI, unapproved AI and unlicensed tracks. Exercise the actual catalogue, selected-job, editor-context, concept-readiness and import SQL: only active, rights-compatible, explicitly approved AI music may be selected. A music approval cannot authorise synthetic effects. Imports preserve generation/approval metadata and the render manifest reports it truthfully; existing records are not bulk-approved. Verify the batch checkbox is unchecked by default, applies per file, starts no request on change, and is never submitted for effects. The single-file form and CLI expose the same explicit choice.

The selected 19-track CSV is a preparation record, not an import or rights-verification result. After deployment and receipt of the audio files, check titles, source links, AI labels and certificate records, then audition a selected track in a new preview/export. This change does not alter audio processing. Local validation includes backend tests, 46 DOM interaction tests, all 38 migrations and actual SQL in isolated PostgreSQL, web TypeScript, production build and the public-release audit. FFmpeg-dependent tests are skipped when FFmpeg is unavailable; deployed music playback remains an acceptance check.


## Story sequence and precise revisions — 2026-11-01

Backend regressions cover exact local volume/caption/removal commands, compound-request fallback, invalid clip/gain rejection, protection conflicts, missing word evidence, post-validation normalization, private context stripping, unchanged source selections, inherited removals with explicit reenable, and local-versus-model execution without automatic no-op retries. Story tests check balanced hints within the existing context cap, preserved dialogue, no long-gap linking, actual selected quotes, legacy unusable timestamps, and selected blooper setup/reaction coverage and order. DOM checks inspect the source outline, timing/evidence labels, review advisories and malformed-entry handling without issuing requests. Real CPU FFmpeg integration tests remain part of the backend suite; NVENC and subjective real-footage quality remain deployed acceptance checks.

After deployment:

1. On a good saved edit, submit **Make clip 2 louder by 6 dB** in targeted revision mode. Confirm the local/zero-AI label, unchanged source ranges and story, and a louder second clip in playback. The total gain cannot exceed +12 dB.
2. Submit **Move captions to the top** with caption protection unlocked. Check both normal captions and existing visible timed caption regions; hidden cues should remain hidden. Open **Local quality review → Recorded story outline** and compare the recorded passages/times with playback.
3. On a test edit with effects/cutaways, submit **Remove effects** or **Remove B-roll**. Confirm the respective cues disappear. Make a later ordinary revision and confirm the removal remains in effect. Camera motion is a separate treatment and is retained by effects removal.
4. Request a specific story adjustment while protecting the sections to keep. Confirm the change report reflects actual selection/treatment changes. If the model returns the same executable cut, expect a clear same-cut notice and no automatic extra call. A **Rebuild story** result that changes only treatment should say so.
5. Generate fresh blooper ideas, select a narrow incident with understandable setup and reaction, and create a preview. Check the complete gag and its timing; no sales payoff should be imposed. Existing saved unfocused concepts need regenerating to test the modern selected-script protection.

These checks do not establish that every requested creative improvement happened, that a story is coherent, or that a gag is funny. Compare real outputs before accepting creative quality. No production hosted requests or live database mutations are part of the local regression run.

Local validation completed: 496 backend tests passed with no skips, including CPU FFmpeg renders and disposable local rclone checks; 47 DOM interaction tests passed; web TypeScript, the production web build, Compose configuration, Python parsing and public-release audit passed. The temporary FFmpeg/rclone test binaries live outside the repository. No deployed service was rebuilt and no hosted edit was requested during this validation.


## Shared retrieval follow-up (Phase 20B) — 2026-11-02

Regressions cover exact word boundaries, normalized words, bounded alias expansion/query terms, generic-direction fallback, camera-named transcript/OCR matches before the source cap, canonical identity with duplicate ranking clues, relevant-group priority, protected speech slots when photos dominate, focused middle passages with close neighbours and source endings, unchanged no-focus sampling, unchanged public inventory budgets, private-vocabulary stripping, and relevant late preview panels within the same four-image allowance. The coverage UI reopens saved sessions without a concept/render request and states that text matching does not establish pictured identity.

An isolated PostgreSQL-compatible engine applies the existing 39 migrations and runs the actual source eligibility and indexed transcript-ranking SQL. Fixtures check collection scoping, archived exclusion, marked Avoid ranges, exact terms versus substrings, and an empty permitted-ID list. This does not touch the production database. Existing B-roll/privacy and real CPU render tests remain regression gates; live GPU latency and subjective relevance require final acceptance.

Keep these tasks for the combined testing pass:

1. Give Find ideas a specific topic already spoken in an older camera-named recording. Check coverage, the exact quoted script and its final story. Compare with blank-direction discovery, which should still explore sources broadly.
2. Use an existing product alias and a collection containing relevant speech, unrelated material and a readable review screenshot. Check that the matching source/recognized-text clues are considered, the collection remains respected and the resulting pictures actually match the spoken product.
3. Try a topic in the middle of a long recording. Inspect the recorded passages for the matching line, intelligible setup and complete ending. A text match alone is not acceptance of story quality.
4. Reopen an older saved concept session. It should work without the new coverage details or another model request. Its chosen script and existing exports should remain unchanged.
5. On a larger library inspect the sampling notice, narrow the direction or choose a collection, then explicitly generate another session if needed. Do not interpret a bounded sample as an exhaustive understanding of all footage.

Source checkpoint verification: 508 backend tests passed with no skips, including real CPU FFmpeg renders; 48 DOM interaction checks passed; all eight source-suite gates passed, including web/agent TypeScript, production build, Compose, Python compilation, public-release audit and patch checks. The 39-migration isolated SQL run additionally exercised the new actual ranking query. These checks made no hosted request and did not mutate production media, jobs, publishing or backup state. The combined real-footage/GPU/pilot pass remains pending after the build sequence.

## Purposeful finishing follow-up (Phase 22) — 2026-11-02

Regressions cover strict nested planner schemas for both engines, camera/caption controls with decorative effects off, replacement of stacked zooms in generated plans, anchored/intentional holds, single-shot validation, new dissolve fallback versus frozen plans, caption cue windows, camera/caption retiming after trims, removal of generated labels without changing local layout, treatment-report timing and one-call worker execution. A real CPU FFmpeg fixture starts with 60fps picture and audible speech, renders an anchored move and a short dissolve with timed caption regions, measures the changed framing and absence of a black flash, and checks four seconds of audible output audio. Existing HDR, word/caption alignment, montage, motion cadence, B-roll and revision-lock regressions remain gates.

Browser interactions check malformed/legacy report handling, kind filtering without requests, explicit seek callbacks, changed-report filter fallback and accurate generated-graphic counts. Removing sounds/graphics makes exactly one explicit revision request; mounting or filtering the timeline makes none. The player seek handler changes position and focuses the video without calling play.

Keep these tasks for the combined real-footage pass after the build sequence:

1. Make an ordinary fresh reel and a high-impact reel with a useful product reveal. Inspect **Treatment timeline** for the actual saved camera moves, cuts, sounds and labels; jump to each and judge relevance and framing in playback. No sound or movement quota proves quality.
2. Give a specific caption-readability instruction, then check the timed band and that important speech remains visible. Check both preview and approved final output; platform overlays still need a real phone review.
3. On a long multi-clip energetic edit, check the short picture dissolve against the recorded speech. Check a single-shot edit and an intentional reaction hold too. Compare a saved frozen version to ensure an exact re-render does not invent a new transition or zoom.
4. On a version with generated text labels/pointers, use **Remove sounds & graphics · zero AI**. Confirm those cues disappear while camera motion, caption placement and mix settings remain. A later revision should retain the removal choice unless explicitly reenabled.
5. Open a legacy preview without a treatment report. Its normal playback, revisions and downloads should remain available. The new report appears on newly rendered manifests; opening an old preview does not regenerate it.

No new hosted edit, production deployment, media mutation or live GPU claim is part of local verification. Automatic tracking, new segmentation models and creative-quality acceptance remain outside this checkpoint.

Source checkpoint verification: 517 backend tests passed with no skips, including real CPU FFmpeg renders and disposable local rclone checks; 51 DOM interaction tests passed; all eight source-suite gates passed, including web/agent TypeScript, production build, Compose, Python compilation, public-release audit and patch checks. The temporary render/test dependencies remain outside the repository. No database migration is added by this increment.

## Evaluated learning follow-up (Phase 24; migration 040) — 2026-11-02

Regression checks cover source-independent scoring, transitive footage overlap, duplicate jobs, conservative group rating deltas, lower-rating blocks, training/legacy exclusion, rule/run identity, unchanged executable edits, missing versus recorded usage, immutable snapshot inputs, actual preview availability and path confinement, rendered-plan provenance, server trial readiness and replay without a second queued candidate. Trial payloads cannot include other changes or omit their baseline. Read-only lab tests cover available files, eligibility reasons, saved ratings and unknown costs. Score submission tests bind server evidence without starting an edit or promoting a rule; owner-only promotion rechecks evidence and rollback retains ratings.

Browser tests cover blocked footage options, cancelled versus explicit trial creation, read-only refresh, exact-version playback without autoplay, cost/request display, saved rating/note restoration, explicit playback attestation and submission, retirement, and unavailable-preview handling. An isolated PostgreSQL-compatible database applies all 40 migrations and runs the actual readiness, source-overlap, trial-reuse, usage-aggregation, evidence-upsert and retention queries. It verifies that legacy evidence defaults to an empty object, proposed trial pairs remain protected, retirement releases ordinary retention, archived jobs are excluded and invalid evidence JSON is rejected. No production data is used.

Keep the following for the combined acceptance pass:

1. After the combined deployment, run the read-only `python3 scripts/verify-phase19-25.py` helper and the normal core live suite. The helper now requires lab contract version 2. Opening `/learning` and **Refresh comparisons** must not create hosted requests or new edits.
2. Use saved feedback on at least three ordinary jobs to propose a matching fixed-template lesson. Inspect its exact directive and scope. It should remain proposed and inactive. These are the training examples; do not reuse their originals for hold-out trials.
3. Prepare three ordinary baseline edits from genuinely separate recordings matching the lesson recipe/style. For this conservative check, do not attach a shared review image or other training/trial source. Confirm a re-upload of identical footage, a training job, local-only job, blooper job or previous lesson trial is unavailable with an explanation.
4. Explicitly create one trial for each eligible baseline. Check that the baseline remains playable and that refreshing or resending the same request does not queue a second candidate. Failed trials do not qualify; ordinary job recovery remains separate. No automatic experiment is started by deployment.
5. Compare each exact pair for story, intact speech, captions, colour, audio and effect relevance. Read token/request totals alongside quality; missing usage should say it is not recorded. Add comparison notes, attest playback and save ratings. Reopen/refresh to check persistence. An unchanged edit cannot earn positive improvement credit merely from a higher score.
6. Promotion should remain disabled/server-rejected until three independent groups have no lower scores and at least one executable improvement. A rolled-back or retired lesson must retain its evidence. After explicit promotion, inspect the next ordinary job's context for the scoped directive; after rollback, confirm it is absent from future context. Existing saved edits and separate tag-derived preferences remain unchanged.
7. In a disposable acceptance fixture, check that routine preview retention protects proposed trial pairs and releases them after retirement/promotion. Do not use production retention deletion as a test shortcut. If a pair's exact files are absent, scoring must be blocked.

This pass evaluates practical quality, not statistical confidence or proof that the rule caused a change. Exact hashes do not recognize every reencoded duplicate. Existing promoted lessons are retained rather than automatically revoked; inspect and explicitly roll back any that fail fresh playback checks. Optional paid critics, self-generated policy text, learned segmentation and autonomous model training are not enabled by this checkpoint.

Source checkpoint verification: 532 backend tests passed with no skips, including real CPU FFmpeg renders and disposable local rclone checks; 54 DOM interaction tests passed; all eight source-suite gates passed. The isolated database run applied all 40 migrations and exercised the actual learning/retention queries. Final focused learning and UI reruns also passed after tightening the read-only schema check and explanatory copy. No service was deployed, learning setting changed, live trial created, rule promoted or production retention/backup action performed.

## Speech precision acceptance — 2026-11-03

After the service rebuild applies migration 041, run `python3 scripts/verify-speech-precision.py`. This is read-only; pending library sources may continue processing in idle time. Check that unavailable sources are not mistaken for confident alignment coverage.

1. Create a new edit from familiar English talking footage. Listen to the beginning and end of every spoken selection, especially quiet consonants, short connecting words, names and numbers. The story should remain intact. Confidence and wider margins reduce risk; human listening is still the acceptance criterion.
2. Include a picture dip between speaking clips. The picture transition should remain visible while the voice stays audible up to the cut. Listen for clicks and clipped syllables. Check Local quality review's sampled join findings; they are suggestions to listen, not a guarantee of a defect.
3. Approve a preview, then let library backfill finish. Re-render the exact edit and export it: the source selections and caption timing must match its saved timing snapshot. Repeat with a delivery variant. Historical edits created before this build should retain their old timing.
4. Use a source twice across jobs. Its cached alignment should be reused without a hosted request. Mixed-language or uncertain words should retain estimates and conservative margins rather than altered transcript text.

The core suite covers CTC repeated-letter alignment, uncertain/interpolated fallback, cache reuse and corruption recovery, immutable partial snapshots, source identity/path checks, background manifest updates, legacy behavior, shared-word joins, rendered audio through picture dips, and advisory output measurements. Real-model checks on private source audio supplement those tests; neither model confidence nor synthetic audio fixtures establish human-labelled timing accuracy.

## Direct subtitle editor acceptance — 2026-11-03

Deploy migration 042 with the normal installer, then run `python3 scripts/verify-subtitle-editor.py`. This check reads the capability and one ready version's caption cards; it does not save a draft, approve a reel, or start a render.

1. Open a ready reel and choose **Edit subtitles** beneath the player. Check that the displayed text matches that version's visible captions, including a legacy preview created before this build. Click timestamps to listen; the current card should highlight during playback. Check both a phone and a desktop.
2. Correct a misspelling in several cards. Typing must not start work. Save the draft, close, refresh and reopen: the corrected text should remain while the video still shows its saved wording. Changing a draft must leave the original transcript and library search untouched.
3. Try find/replace, split at the text cursor, merge next, hide, per-caption position, Undo and Reset draft. A split estimates timing inside the previous interval; listen to check it. Hiding a caption must leave the recorded voice intact. Opening the editor on a phone should show a caption without first requiring a long scroll; Save and Apply should remain reachable.
4. Apply the draft. Exactly one local preview should be queued, with no AI editing request. Compare the finished version: corrected text/positions should appear, hidden captions should disappear, and the media cut, music and effects should stay intact. Earlier previews and approvals should remain available.
5. Re-render the exact edit, export it and download the VTT/package. Check corrected text in each output. Make a shorter delivery variant and check that it uses the corresponding corrected prefix without captions extending beyond the video.
6. Open the same subtitle draft in two tabs. Save in the first, then try saving in the second: the second must retain its unsaved text and report a conflict. A newer story version must prevent applying an older draft over it. Duplicate Apply requests must point to the same queued run.

Timed user captions are tied to their saved source selections and audio joins. A changed cut resets overrides and shows a notice; this protects against attaching a caption to different speech. Text-only corrections preserve the existing interval; this build does not promise new per-word timing for rewritten text. The saved video remains burned-in until a local render completes.
