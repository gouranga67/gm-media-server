# Phase 2 report — local runtime stack

Completed: 2026-10-22 (Australia/Brisbane)

Phase 2 is running under the root-managed systemd unit.

## What is ready

- `compose.yaml` defines PostgreSQL, Redis, migration, media initialization, API, worker, tusd, and web-agent services.
- PostgreSQL and Redis persist data in named volumes and are reachable only on the private backend network.
- The web service is the only application service with a host port, bound to `127.0.0.1:3000` for eventual Tailscale Serve proxying.
- The API exposes liveness and dependency-aware readiness checks.
- The worker emits a Redis heartbeat and waits on a dedicated queue. It does not process media until the validated task implementation is added in Phase 4.
- The initial PostgreSQL migration defines projects, assets, jobs, events, edit plans, and approvals.
- The media initializer creates controlled storage areas and assigns them to the non-root application UID.
- The application containers drop Linux capabilities, use `no-new-privileges`, and have read-only root filesystems where practical.
- A root-managed systemd unit controls Compose. Application containers do not receive `/var/run/docker.sock`.

## Why there are several services

Each service owns one kind of responsibility:

- **PostgreSQL** is durable truth. A reboot must not lose a job or an editorial decision.
- **Redis** is a fast wake-up signal and queue. It can be rebuilt from durable job state.
- **tusd** handles interrupted phone uploads without forcing a large file to restart from zero.
- **FastAPI** validates identities, state changes, file references, and later the agent's edit plan.
- **Worker** performs slow media analysis and rendering without freezing the web interface.
- **Next.js + Eve** provides the phone UI and conversational editor.

The Lenovo can therefore restart one failed part without merging all responsibilities into one fragile process.

## Verification completed

- Compose configuration: valid.
- Next.js standalone build: passed on Node 24.22.0.
- Next.js version: 16.4.2.
- TypeScript version: 5.9.3.
- Python source parsing: passed on all core service modules.
- systemd unit validation: passed; the restricted shell emitted only capability-socket warnings.
- Production npm audit: zero known vulnerabilities.

## Live verification

- The systemd unit is enabled and its result is successful.
- PostgreSQL, Redis, tusd, API, worker, and web-agent are healthy.
- Migration and media-initialization jobs exited successfully.
- A controlled service restart recovered the full stack.
- The web health endpoint and home page return HTTP 200.
- Only `127.0.0.1:3000` is published on the host; internal service ports are not exposed.
- The service journal contains no warnings from the successful start.

The `gm` login intentionally remains unable to control Docker directly. GPU access inside the future media-worker image and a complete host-reboot recovery drill remain later-phase checks because the Phase 2 worker does not yet contain media tooling.

First activation note: the initial live start showed that the official Redis entrypoint needs its normal startup privileges to initialize the persistent `/data` volume before it drops to the `redis` user. The blanket capability drop was removed for that container; it still has `no-new-privileges`, a read-only root filesystem, a private-only network, and no published port.
