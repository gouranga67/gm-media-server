#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this importer as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
transfer_file=/tmp/gm-studio-chatgpt.json

if [[ ! -f "$transfer_file" || -L "$transfer_file" ]]; then
  printf 'Expected a regular credential file at %s\n' "$transfer_file" >&2
  exit 1
fi

chmod 0600 "$transfer_file"
docker compose --project-directory "$project_root" --profile tools run --rm --no-deps \
  --volume "$transfer_file:/import/chatgpt.json:ro" \
  chatgpt-enroll python -m app.chatgpt_enroll \
  --import-credentials /import/chatgpt.json

if command -v shred >/dev/null 2>&1; then
  shred --remove "$transfer_file"
else
  rm --force "$transfer_file"
fi
printf 'Removed the transferred credential from %s after successful import.\n' "$transfer_file"
