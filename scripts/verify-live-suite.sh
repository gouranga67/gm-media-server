#!/usr/bin/env bash
set -u

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

# Once private access is enabled, direct loopback requests are intentionally
# rejected. Run browser-facing checks through the configured Tailscale Serve
# origin so the suite exercises the same trusted boundary as a phone.
if [[ -z ${GM_MEDIA_URL:-} && -f .env ]]; then
  private_media_url=$(python3 - .env <<'PY'
import sys
from pathlib import Path

values = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

if values.get("TAILSCALE_AUTH_REQUIRED", "").lower() == "true" and values.get("APP_ORIGIN"):
    print(f"{values['APP_ORIGIN'].rstrip('/')}/api/media")
PY
  )
  if [[ -n "$private_media_url" ]]; then
    export GM_MEDIA_URL="$private_media_url"
  fi
fi

include_render=false
if [[ "${1:-}" == "--confirm-render-and-ai" ]]; then
  include_render=true
elif [[ $# -gt 0 ]]; then
  printf 'Usage: sudo %s [--confirm-render-and-ai]\n' "$0" >&2
  exit 2
fi

if ! docker info >/dev/null 2>&1; then
  printf 'Docker is not accessible. Run this live suite with sudo.\n' >&2
  exit 2
fi

passed=0
failed=0
failed_labels=()

run_check() {
  local label=$1
  shift
  printf '\n== %s ==\n' "$label"
  if "$@"; then
    passed=$((passed + 1))
    printf 'PASS  %s\n' "$label"
  else
    failed=$((failed + 1))
    failed_labels+=("$label")
    printf 'FAIL  %s\n' "$label" >&2
  fi
}

check_migration_runner() {
  local container_id state
  container_id=$(timeout --foreground --kill-after=2s 10s \
    docker compose ps -aq migrate) || return $?
  if [[ -z "$container_id" ]]; then
    printf 'Migration runner container was not found.\n' >&2
    return 1
  fi
  state=$(timeout --foreground --kill-after=2s 10s \
    docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container_id") || return $?
  printf 'Migration runner state: %s\n' "$state"
  [[ "$state" == "exited 0" ]]
}

run_check "Service and container health" timeout --foreground --kill-after=10s 120s ./scripts/verify-phase2.sh
run_check "Database migrations 010-027" check_migration_runner
run_check "Backend unit and local render tests" timeout --foreground --kill-after=10s 300s docker compose run --rm --no-deps \
  -v "$project_root/services/core/tests:/app/tests:ro" \
  worker python -m unittest discover -s /app/tests -p 'test_*.py' -v
run_check "Existing media analysis" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase4.py
run_check "Reusable server-library references" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase6c.py
run_check "Library concept discovery readiness" timeout --foreground --kill-after=10s 120s python3 scripts/verify-library-concepts.py
run_check "Non-destructive exact-duplicate audit" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase6c2.py
run_check "Source-evidence catalogue and search" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase6d.py
run_check "Local semantic visual index and search" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase6e.py
run_check "Reversible media-library organization" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase8.py
run_check "Complete job history and test classification" timeout --foreground --kill-after=10s 300s python3 scripts/verify-job-history.py
run_check "Editorial workspace, brand kits, and presets" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase11.py
run_check "Product controls, access roles, and safe retention" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase12.py
run_check "Local story intelligence, engagement, and edit guidance" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase13.py
run_check "Local feedback learning loop" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase14.py
run_check "Rights-aware music and creative effects" timeout --foreground --kill-after=10s 300s python3 scripts/verify-phase16.py

if $include_render; then
  printf '\nThe opt-in lane creates/revises edit runs, performs GPU renders, and may use the connected ChatGPT plan.\n'
  run_check "Deterministic preview renderer" timeout --foreground --kill-after=30s 1800s python3 scripts/verify-phase5.py
  run_check "Talking-head revision and final delivery" timeout --foreground --kill-after=30s 1800s python3 scripts/verify-phase6.py
  run_check "Montage delivery, captions, models, and usage" timeout --foreground --kill-after=30s 1800s python3 scripts/verify-phase6b.py
  run_check "Creative profiles and zero-AI delivery variants" timeout --foreground --kill-after=30s 1800s python3 scripts/verify-phase10.py
else
  printf '\nSKIP  Render/AI lane (rerun with --confirm-render-and-ai after the core suite passes)\n'
fi

printf '\nLive-suite summary: %d passed, %d failed\n' "$passed" "$failed"
if ((failed > 0)); then
  printf 'Failed checks:\n'
  printf '  - %s\n' "${failed_labels[@]}"
fi
((failed == 0))
