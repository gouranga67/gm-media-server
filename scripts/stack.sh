#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

if [[ ! -f .env ]]; then
  printf 'Missing .env. Copy .env.example and replace its placeholder password.\n' >&2
  exit 1
fi

case "${1:-}" in
  config)
    exec docker compose config
    ;;
  up)
    exec docker compose up --detach --build
    ;;
  down)
    exec docker compose down
    ;;
  status)
    exec docker compose ps
    ;;
  logs)
    exec docker compose logs --follow --tail=200 "${2:-}"
    ;;
  *)
    printf 'Usage: %s {config|up|down|status|logs [service]}\n' "$0" >&2
    exit 2
    ;;
esac
