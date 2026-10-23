#!/usr/bin/env bash
set -euo pipefail

target="http://127.0.0.1:3000"

if [[ "${1:-}" != "--apply" ]]; then
  printf 'Current Tailscale Serve configuration:\n\n'
  tailscale serve status || true
  printf '\nNo changes made. After reviewing the status, apply the GM Studio root proxy with:\n'
  printf '  sudo %s --apply\n' "$0"
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run this command with sudo so tailscaled can persist the Serve configuration.\n' >&2
  exit 1
fi

if ! curl --fail --silent --show-error --max-time 5 http://127.0.0.1:3000/api/health >/dev/null; then
  printf 'GM Studio is not healthy on 127.0.0.1:3000; Serve was not changed.\n' >&2
  exit 1
fi

tailscale serve --bg --yes "$target"
printf '\nPersisted private HTTPS proxy:\n\n'
tailscale serve status
