# GM Studio

GM Studio is a self-hosted, phone-first editing appliance. Upload your own footage and photographs, let a bounded editor agent propose an edit, and render the result locally with deterministic media tools. It does not generate replacement images, video, voices, music, or footage.

The project is open source under [Apache-2.0](LICENSE). Your deployment remains private: source media, exports, database contents, `.env`, and ChatGPT credentials are runtime data and must never be committed.

> **Security status:** GM Studio currently assumes a trusted, private Tailscale network. Authentication and recovery hardening are Phase 7 work. Do not expose it through Tailscale Funnel, public port forwarding, or a public reverse proxy.

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

The detailed design is in [the architecture plan](docs/architecture-plan.md), and current progress and exit criteria are in [the build phases](docs/build-phases.md).

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

## Verify the build

Host-only checks:

```bash
npm run typecheck:web
npm run build:web
docker compose config --quiet
python3 -m py_compile services/core/app/*.py scripts/*.py
./scripts/check-public-release.sh
```

Core unit tests use Python 3.13 and the dependencies in `services/core/requirements.txt`; the public CI workflow provisions that isolated environment automatically.

Live acceptance checks require a configured and running stack:

```bash
python3 scripts/verify-phase3.py
python3 scripts/verify-phase4.py
python3 scripts/verify-phase5.py
python3 scripts/verify-phase6.py
```

The Phase 3 check exercises interrupted/resumed tus uploads, Phase 4 verifies real-media analysis, Phase 5 proves strict edit-plan validation plus a downloadable deterministic preview, and Phase 6 exercises revision, approval, and full delivery packaging.

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
