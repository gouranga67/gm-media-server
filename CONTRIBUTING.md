# Contributing to GM Studio

GM Studio welcomes focused improvements to its private, source-only media workflow.

## Ground rules

- Do not add image, video, voice, or music generation capabilities.
- Never include real user footage, credentials, tailnet addresses, database dumps, or machine-specific identifiers in an issue, test, fixture, or commit.
- Preserve the trust boundary: models propose a constrained edit plan; trusted code validates it; deterministic tools render it.
- Keep application ports private by default and do not give agents arbitrary shell, filesystem, Docker, or network access.
- Add tests for changes to validation, upload recovery, durable processing, or path handling.

## Development checks

Use Node 24 and Docker Compose. Before opening a pull request, run:

```bash
npm ci
npm run typecheck:web
npm run build:web
docker compose config --quiet
python3 -m py_compile services/core/app/*.py
PYTHONPATH=services/core python3 -m unittest discover -s services/core/tests -v
./scripts/check-public-release.sh
```

Install `services/core/requirements.txt` in an isolated Python 3.13 environment before running the unit-test command. Container-backed integration checks require a configured `.env` and a suitable NVIDIA host. Never commit that environment file.

## Licensing

Unless explicitly stated otherwise, contributions are submitted under Apache-2.0, the repository's license.
