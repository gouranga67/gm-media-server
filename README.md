# GM Studio

GM Studio is a self-hosted, phone-first editing appliance. Upload your own footage and photographs, let a bounded editor agent propose an edit, and render the result locally with deterministic media tools. It does not generate replacement images, video, voices, music, or footage.

The project is open source under [Apache-2.0](LICENSE). Your deployment remains private: source media, exports, database contents, `.env`, and ChatGPT credentials are runtime data and must never be committed.

> **Security boundary:** GM Studio listens only on host loopback and is published through private Tailscale Serve, never Funnel. The deployed web layer requires Serve's stripped-and-injected Tailscale identity header to match the configured owner or an active member invited by that owner. Do not add public port forwarding or a public reverse proxy.

## How it works

```text
Phone
  | private HTTPS over Tailscale
  v
Web/PWA ---> API ---> PostgreSQL
  |           |
  |           +----> Redis work signal ---> GPU media worker
  |                                      |
  +----> resumable upload service -------+---> local media storage

Editor model ---> constrained JSON edit plan ---> validator ---> FFmpeg renderer
```

- The web app accepts resumable phone uploads and returns downloadable MP4 previews.
- Local Whisper, FFmpeg, and the NVIDIA GPU analyze and render supplied media.
- The model sees structured project facts, transcripts, and contact sheets—not arbitrary host files.
- The model can reference only registered asset IDs, valid time ranges, and approved edit operations.
- Trusted code validates the edit decision list and builds FFmpeg arguments. The agent receives no shell or Docker access.

Start with the illustrated [system architecture guide](docs/system-architecture-guide.md), or open its [print-ready PDF edition](docs/GM-Studio-System-Architecture-Guide.pdf). The detailed design is in [the architecture plan](docs/architecture-plan.md), current progress and exit criteria are in [the build phases](docs/build-phases.md), and the layered acceptance process is in [the testing plan](docs/testing-plan.md).

The [26 October system audit and roadmap](docs/system-audit-and-roadmap.md) reviews all page routes, model evidence, compute efficiency, editing tools and proposed next phases. Read the [illustrated audit PDF](docs/GM-Studio-System-Audit-and-Roadmap.pdf) or its [browser edition](docs/system-audit-and-roadmap.html). Proposed features are clearly separated from inspected behavior.

## Requirements

- Linux host with Docker Engine and Docker Compose v2
- NVIDIA driver and NVIDIA Container Toolkit for GPU acceleration
- Tailscale for private phone access
- Node.js 24 and npm 11 for host-side web checks
- Enough local disk for immutable originals and derived media

The reference build uses an NVIDIA RTX 3050. CPU fallbacks exist for rendering, but GPU support is the intended deployment.

## Configure and deploy

Clone the repository to any absolute path, then create a private environment file:

```bash
cp .env.example .env
chmod 600 .env
```

Replace every placeholder secret and set `APP_ORIGIN` to the HTTPS name served inside your tailnet. Validate before starting:

```bash
npm ci
npm run doctor
docker compose config --quiet
```

Install the boot-managed stack from the repository root:

```bash
sudo ./scripts/install-service.sh
```

The installer renders the current absolute repository path into a root-owned systemd unit. Compose publishes the web service on loopback only; route that port privately with Tailscale Serve.

## Connect ChatGPT plan sharing

The primary editor can use a user's eligible ChatGPT plan through Sign in with ChatGPT. This is not an API key and does not make ChatGPT responsible for storage or rendering. Local Whisper still transcribes, and local FFmpeg/NVIDIA still renders.

OAuth must complete on the computer running the browser. Copy the enrollment helper from the server to that computer, run it locally, then securely copy its one-time transfer file back. For example, from PowerShell:

```powershell
scp your-user@your-server:/path/to/gm-media-server/scripts/chatgpt-enroll-local.py .
py -m pip install "PyJWT[crypto]==2.10.1"
py .\chatgpt-enroll-local.py
scp .\gm-studio-chatgpt.json your-user@your-server:/tmp/gm-studio-chatgpt.json
```

Then run on the server from the repository root:

```bash
sudo ./scripts/import-chatgpt.sh
```

The importer validates the identity, assigns a stable VM host identifier, stores the rotating credential in the private `auth-data` volume with mode `0600`, and removes the server-side transfer file. Delete the remaining transfer file from the browser computer after a successful import.

The interface identifies work that used the ChatGPT plan and links to ChatGPT usage settings. Requests use streaming and disable OpenAI response storage. Vercel AI Gateway is an optional paid fallback and stays disabled unless both its enable flag and API key are deliberately configured.

For the upstream requirements, see OpenAI's [open-source token sharing guide](https://developers.openai.com/siwc/token-sharing-open-source) and [self-hosted VM flow](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).

## Organize source media

Open `/library` to browse Talking footage, B-roll, Photos, Audio, or Unsorted videos. Select videos and choose **Label videos as…** to separate spoken footage from visual cutaways. These labels reach the editor as user intent; they do not replace source evidence or the checks against using a different speaking take as silent B-roll.

Use the pencil beside a file for a readable display name, or select several and **Rename batch** (for example, `Cream close-up 001`). Original filenames, storage paths, hashes, and existing edits remain unchanged. New uploads can receive a name prefix and footage role before transfer. Names and roles also appear in the New job picker.

**Move to Trash** hides selected originals from the library and future jobs after confirmation. Restore them from the Trash view. This keeps originals on disk and preserves existing jobs; it is not permanent deletion or disk reclamation. Reviewed exact duplicates are grouped by default, with **Show repeated uploads** available when managing copies. Use **Duplicate audit** for the separate verified storage-sharing workflow.

**Categories** work for photos, videos and audio: Reviews, Products, Scenes, Documents, Other, or Uncategorized. Select files and use **Categorize files as…**, or choose Category in a file's details. Use the category filter alongside Photos/B-roll/Talking footage. Talking/B-roll footage labels remain video-specific.

**Auto-sort** proposes descriptive names, categories and video roles using stored transcripts and small preview sheets, for example “Talking about soap”, “Cream B-roll”, or “Image of customer review”. Select up to 24 files and choose **Auto-sort selected**, or use Auto-sort above the library to prepare the next batch from the current view. Press **Suggest names & categories** to make one bounded AI request. Review the names, edit them if needed, select the suggestions you want, then **Apply selected suggestions**. Originals and existing jobs are not renamed on disk or changed. Custom names and manual labels are kept by default; an explicit checkbox allows replacing existing names. Notes/favorites survive and suggested tags are merged without displacing existing tags. Uncertain proposals are unchecked. Text-only mode shares no frames and may not identify anonymous pictures.

Auto-sort sessions are saved separately from editing jobs, can be reopened without another AI call, and count toward the usage dashboard and studio budgets. Files must finish catalogue analysis first. Stale metadata or trashed sources prevent application rather than silently overwriting later edits. No automatic paid retry or automatic metadata application runs. Deploy migration 028 and run `python3 scripts/verify-library-organization.py` for read-only live readiness checks.

After deploying migration 025, `python3 scripts/verify-phase8.py` checks names, roles, collection filtering, atomic batch failures, Trash/restore, provenance, and preview download. It restores the original metadata afterward and makes no AI calls.

## Find reel ideas from existing footage

Open **Library → Find reel ideas** (`/concepts`). Add a batch of media there or in the library, then wait for its local speech/catalogue analysis. Leave Direction empty for discovery across the ready library, or choose a collection, audience, and subject. **Generate reel ideas** makes one explicit, bounded request using stored transcripts/metadata and, in Hybrid mode, small preview sheets. Original files remain on the server.

The saved options show recorded script passages with source/time links and proposed supporting pictures. Script words come from cited transcript records, not generated narration. Select one or two options, choose effects/music/platform, then **Create previews**. Each selection becomes a separate ordinary editing job; you review the result before export. Repeated submissions reuse existing sessions/jobs. New concepts and their measured token usage are separate from editing history, and their usage counts toward studio budgets.

Discovery considers up to 60 unique ready sources per request, spreads speech evidence across recordings and their beginnings/endings, and reports actual coverage. It does not promise to inspect the whole library in a single model call. Use a collection or focus to explore a larger library. Fewer than three options may be returned when that is all the evidence supports. Background processing failures and interrupted model calls are visible; ambiguous model requests are not automatically retried.

After deploying migration 026, run `python3 scripts/verify-library-concepts.py` for read-only readiness checks with no model calls. Generating concepts and rendering selected previews are explicit actions in the browser.

Choose **Reel type → Bloopers & outtakes** to find possible mistakes, restarts, lost lines, repeated takes and laughter in the stored transcript. The local scan includes nearby setup/recovery from the same recording, excludes labelled B-roll from spoken candidates, and adds no model calls. If no clues are found, no concept request is queued. Candidate scripts show the reason and source/time links; review them, choose one or two, then create previews as usual. The editor explicitly preserves recorded outtakes rather than substituting clean takes. Empty waiting is still trimmed, and the usual approval/export step remains.

These are possible outtakes, not verified mistakes or factual error detection. Repeated takes can be intentional; purely visual gags, ASR mistakes and laughter omitted by transcription may be missed. A concept request may return no worthwhile options when weak clues do not support a reel. The existing 60-source/36,000-character discovery limits apply; narrow by collection for targeted scans. Normal story discovery keeps its clean-take behavior. This addition requires migration 027.

## Import rights-approved music

GM Studio can install the reviewed starter catalogue or accept your own non-synthetic audio files with recorded licence, commercial-use confirmation, attribution, and permitted platforms.

To install the curated starter library without uploading files individually:

```bash
python3 scripts/import-creative-starter-library.py
```

It imports 16 Kenney CC0 sound effects, 20 Google Noto emoji PNGs under Apache-2.0, and two CC0 instrumental tracks (Revelation and Happy Lullaby). Existing music is retained. Downloads and archive members are SHA-256 pinned in `docs/creative-starter-library.json`; repeated runs skip exact duplicates, including archived records. `--download-only` checks the files without changing the server. The importer uses the existing private owner connection, makes no model calls, and saves downloads in the system temporary cache. Delivery ZIPs include asset credits and the Apache licence when Noto artwork is used. Third-party media stays outside Git.

The normal workflow is the **Creative** page at `/creative`. Download a track from its official Pixabay page, upload the file there, and paste the same page URL into the rights record. The page also accepts licensed sound effects, meme sounds, PNG/JPEG/WebP stickers, GIFs, and meme images. The command below remains available for server-side music imports.

```bash
./scripts/import-music.sh /absolute/path/to/track.mp3 --help
```

Example metadata shape:

```bash
./scripts/import-music.sh /absolute/path/to/track.mp3 \
  --title "Track title" \
  --artist "Artist name" \
  --mood optimistic \
  --energy medium \
  --license-name "Your cross-platform commercial licence" \
  --license-source-url "https://example.com/licence" \
  --license-proof "Receipt or licence record reference" \
  --platform all_social \
  --commercial-use-confirmed
```

Importing confirms only what you record; it does not independently grant or verify rights. Tracks remain unavailable to the agent unless they are active, marked for commercial use, non-synthetic, and compatible with the job's selected platform.

## Recovery operations

The production appliance uses two copies of the same encrypted Restic repository: the prepared USB at `/mnt/gm-backup` and a verified mirror in OneDrive. The OneDrive side contains encrypted repository objects, not directly playable media. Private web access is restricted to the configured Tailscale owner, and `/system` reports the USB snapshot, off-site mirror, queues, storage, GPU, and reboot-recovery state.

The one-time and destructive acceptance steps are documented in [the testing plan](docs/testing-plan.md). In order, configure private access, enroll/import OneDrive, then run the deliberate reboot recovery drill. Never paste the Restic recovery key or the temporary rclone configuration into chat, email, logs, or the repository.

## Verify the build

Run the complete host-only source gate as the normal user:

```bash
./scripts/verify-source-suite.sh
```

The API and public CI use Python 3.13. The pinned CUDA worker base currently supplies Python 3.10, so shared service code is kept compatible with both runtimes. The live suite runs the backend and FFmpeg integration tests inside that production worker image.

After deployment, the live core suite verifies service health, migrations, containerized backend tests, existing media analysis, reusable library references, duplicate auditing, and source-evidence search:

```bash
sudo ./scripts/verify-live-suite.sh
```

The render and editor lane is deliberately opt-in because it creates edit versions, uses GPU time, and may consume connected ChatGPT plan allowance:

```bash
sudo ./scripts/verify-live-suite.sh --confirm-render-and-ai
```

Individual live acceptance helpers remain available:

```bash
python3 scripts/verify-phase3.py
python3 scripts/verify-phase4.py
python3 scripts/verify-phase5.py
python3 scripts/verify-phase6.py
python3 scripts/verify-phase6b.py
python3 scripts/verify-phase6c.py
python3 scripts/verify-phase6c2.py
python3 scripts/verify-phase6d.py
python3 scripts/verify-phase6e.py
python3 scripts/verify-phase10.py
python3 scripts/verify-phase11.py
python3 scripts/verify-phase12.py
python3 scripts/verify-phase13.py
python3 scripts/verify-phase14.py
python3 scripts/verify-phase16.py
```

The Phase 3 check exercises interrupted/resumed tus uploads, Phase 4 verifies real-media analysis, Phase 5 proves strict edit-plan validation plus a downloadable deterministic preview, and Phase 6 exercises revision, approval, and full delivery packaging. Phase 6B verifies a deployed montage plus its model catalogue and usage ledger. Phase 6C verifies zero-copy reuse and the non-destructive duplicate audit; Phase 6D verifies catalogue backfill and provenance-bearing text search; Phase 6E verifies local semantic visual search with source-frame evidence. Phase 9 verifies checksum-gated physical storage sharing while preserving every asset record and historical path. Phase 10 verifies reusable Creative Profiles and locally rendered square/vertical/landscape variants without another model call. Phase 11 verifies the clip-level editorial timeline, managed brand kits, publishing presets, and profile management without consuming model tokens. Phase 12 verifies the product dashboard, Tailscale-backed roles, job archive/restore, AI budgets, operator audit, and derived-file retention with a database-enforced zero-original guarantee. Phase 13 verifies cached local story moments and source-backed engagement guidance. Phase 14 verifies the local learning loop. Phase 16 verifies rights-aware creative libraries, platform filtering, effect controls, and zero additional model usage.

The root URL is the studio dashboard. `/welcome` explains initial setup, `/jobs` manages active and archived work, `/operations` controls workload and retention, and `/access` manages invited Tailscale identities. Owner/editor/viewer permissions reuse Tailscale authentication; GM Studio does not store passwords.

## Repository map

| Path | Purpose |
|---|---|
| `agent/` | Bounded editor instructions and typed tools |
| `apps/web/` | Phone-friendly Next.js interface |
| `services/core/` | API, durable workers, validation, and rendering |
| `deploy/` | Portable systemd service template |
| `docs/` | Architecture, phase status, and operating explanations |
| `scripts/` | Deployment, diagnostics, enrollment, and acceptance checks |

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes and [SECURITY.md](SECURITY.md) before deploying or reporting a vulnerability.
