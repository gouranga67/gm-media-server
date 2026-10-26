# Reference server map

This document explains the system in physical terms. The [26 October audit and roadmap](system-audit-and-roadmap.md) contains the current evidence flow, limitations and proposed next phases.

## Hardware layer

- **1 TB NVMe:** originals, proxies, analysis results, previews, exports, application data, and containers currently share one physical disk. It needs a second backup copy before holding unique footage.
- **Intel CPU and 14 GiB RAM:** run the web app, API, database, queue, and general analysis. The build will limit concurrency so these remain responsive.
- **RTX 3050 with 4 GiB VRAM:** accelerates video decode/encode and one modest transcription task. It is not large enough to host a strong multimodal editor model alongside media processing.
- **Ethernet/Wi-Fi:** carries local traffic. Tailscale creates the private encrypted route without opening the application to the public internet.

## Software layers

1. **Ubuntu and systemd** boot the machine and core services.
2. **Tailscale** identifies approved devices and supplies private connectivity.
3. **Docker Compose** isolates and restarts the application services.
4. **PostgreSQL** records durable truth: projects, assets, job states, edit plans, approvals, and provenance.
5. **Redis** carries short-lived work notifications; losing Redis must not lose the job record.
6. **tusd** accepts resumable phone uploads into controlled storage.
7. **FastAPI** enforces job state, permissions, paths, and edit-plan validation.
8. **Python worker + FFmpeg** inspect and render the actual media, using the GPU when appropriate.
9. **Core editor planner** sends a bounded brief, source evidence and selected preview images through the connected model transport, then validates the returned edit decision list. The separate **Eve chat agent** offers narrow API tools as an optional conversational surface; it does not manipulate files directly.
10. **Next.js PWA** is the phone interface for uploads, progress, review, and downloads.

## Where data travels

- Original files travel from the phone directly to the Lenovo through the tailnet.
- Originals and final renders stay on the Lenovo unless you explicitly download or back them up.
- In hybrid mode, the editor model may receive transcript text, metadata, and selected low-resolution frames. It does not receive original media files.
- In local-only mode, no media-derived material leaves the server; early editing quality will rely more heavily on fixed recipes and human review.

## Trust boundaries

- The phone and Tailscale identity may request operations through the web application.
- The API is the only authority that changes job state.
- The worker receives validated task parameters and restricted filesystem mounts.
- Agent output is treated as untrusted data until the API validates its schema and referenced source ranges.
- Secrets remain outside Git and outside agent context.
