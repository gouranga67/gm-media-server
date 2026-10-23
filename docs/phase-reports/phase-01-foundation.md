# Phase 1 report — repository foundation

Completed: 2026-10-22 (Australia/Brisbane)

## What was built

- A repository entry point, live build plan, detailed architecture, and physical system map.
- Node 24 runtime pins and a secret-safe environment template.
- Git and Docker exclusions for credentials, dependencies, generated output, and media.
- A read-only server doctor and repeatable TypeScript check.
- An offline-safe web build that does not fetch Google Fonts.

## How this layer works

This phase is the blueprint and control surface. It does not edit media yet. It makes every later service explicit and gives the server repeatable checks so a reboot or interrupted SSH session does not leave the project state ambiguous.

The Lenovo currently has two software contexts:

1. The **host** runs Ubuntu, Docker, Tailscale, the NVIDIA driver, and system services.
2. The **project** contains versioned application definitions. Later, Docker turns these definitions into isolated running containers.

The host's default Node 22 remains untouched. The project declares Node 24 and uses Node 24 in its future container, which avoids changing a system runtime that other host tools may use.

## Verification

- Host-visible doctor: 9 passes, 3 expected warnings, 0 failures.
- TypeScript: passed under Node 24.22.0.
- Git exclusions: dependency, cache, secret, build, and media paths are ignored.
- Production web build: passed after removing its external font download and selecting the restricted-server-compatible Webpack build path.

The three doctor warnings were expected at this stage: the host defaults to Node 22, `.env` had not yet been configured, and the `gm` account cannot control Docker directly.
