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

## Gate 2 — deploy and live core

Status: **Passed on 2026-10-24.** All 10 live core gates passed, including 61 backend tests. The deployed catalogue, exact-duplicate audit, local visual index, managed library, and complete job history were verified without deleting an original.

Deploy once, then run the live suite with Docker access:

```bash
cd gm-media-server
sudo ./scripts/install-service.sh
sudo ./scripts/verify-live-suite.sh
```

This checks service health, migrations 010–019, backend unit/integration tests inside the pinned CUDA worker image, an existing real analysis manifest, reusable-library references, exact-duplicate calculations, the content catalogue backfill/search API, local semantic visual indexing, reversible managed-library operations, complete non-destructive job-history classification, the Phase 11 editorial workspace, the Phase 12 product controls, and the Phase 13 local story index. The Phase 12 helper round-trips a temporary member, operational limits, and job archive state. It runs retention behind a 10-year threshold and requires `originals_removed: 0`. The Phase 13 helper waits for local moment-card backfill, attaches an existing source to a verification job, and proves exact source ranges, engagement scores, clean edit guidance, story coverage, and zero additional model calls. The test location matters: it catches compatibility differences between the Python 3.13 API image and the CUDA image's Python runtime.

The library verifier uses one stable verification project and job on every run. The duplicate verifier may store a canonical preference, but neither helper deletes, moves, merges, or rewrites an original media file. The catalogue and visual-search tests are read-only after their background backfills; the visual test reads a generated source-frame derivative but never modifies an original.

Phase 9 storage acceptance is a separate explicit operation because it changes physical allocation while preserving every logical original path. After a current encrypted backup, run `python3 scripts/verify-phase9.py --confirm-storage-optimization`. It re-hashes a reviewed exact-copy group, atomically shares its disk blocks, verifies that all records remain, and confirms that the group has no unoptimized bytes left.

## Gate 3 — opt-in render and editor acceptance

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
