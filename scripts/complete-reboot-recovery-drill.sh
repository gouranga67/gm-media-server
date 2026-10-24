#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'The reboot recovery verifier must run as root.\n' >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
status_directory=/var/lib/gm-media-server
pending_file="$status_directory/reboot-recovery-pending.json"
result_file="$status_directory/reboot-recovery-drill.json"

if [[ ! -f "$pending_file" ]]; then
  exit 0
fi
readarray -t pending < <(python3 - "$pending_file" <<'PY'
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in ("run_id", "job_id", "version", "boot_id_before", "started_at"):
    print(document[key])
PY
)
run_id=${pending[0]:-}
job_id=${pending[1]:-}
version=${pending[2]:-}
boot_id_before=${pending[3]:-}
started_at=${pending[4]:-}
boot_id_after=$(cat /proc/sys/kernel/random/boot_id)
uuid_pattern='^[0-9a-fA-F-]{36}$'
if [[ ! "$run_id" =~ $uuid_pattern || ! "$job_id" =~ $uuid_pattern || ! "$version" =~ ^[0-9]+$ ]]; then
  printf 'The pending reboot drill file is invalid.\n' >&2
  exit 1
fi

cd "$project_root"
state=failed
message="The recovered render did not finish within 20 minutes."
preview_path=""
attempts=0
deadline=$((SECONDS + 1200))
while (( SECONDS < deadline )); do
  row=$(docker compose exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -At -F '|' -c \"SELECT status, COALESCE(preview_path, ''), attempts, COALESCE(error, '') FROM edit_runs WHERE id = '$run_id';\"")
  IFS='|' read -r run_status preview_path attempts run_error <<<"$row"
  if [[ "$run_status" == "ready" ]]; then
    if [[ "$boot_id_before" == "$boot_id_after" ]]; then
      message="The render completed, but the machine boot ID did not change."
    elif [[ -z "$preview_path" ]]; then
      message="The recovered run is ready but has no preview path."
    elif docker compose exec -T worker test -s "/media/$preview_path"; then
      state=passed
      message="The interrupted render resumed after a full server reboot and produced a readable preview."
    else
      message="The recovered run is ready but its preview file is missing."
    fi
    break
  fi
  if [[ "$run_status" == "failed" ]]; then
    message="The recovered render failed: ${run_error:-unknown worker error}"
    break
  fi
  sleep 5
done

completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
temporary=$(mktemp --tmpdir gm-reboot-result.XXXXXX)
python3 - "$state" "$message" "$run_id" "$job_id" "$version" "$attempts" "$preview_path" "$started_at" "$completed_at" "$boot_id_before" "$boot_id_after" >"$temporary" <<'PY'
import json
import sys

state, message, run_id, job_id, version, attempts, preview_path, started_at, completed_at, before, after = sys.argv[1:]
print(json.dumps({
    "status": state,
    "message": message,
    "run_id": run_id,
    "job_id": job_id,
    "version": int(version),
    "attempts": int(attempts or 0),
    "preview_path": preview_path or None,
    "started_at": started_at,
    "completed_at": completed_at,
    "boot_id_changed": before != after,
}, indent=2))
PY
install -o root -g root -m 0644 "$temporary" "$result_file"
rm -f -- "$temporary" "$pending_file"
if systemctl list-unit-files gm-media-health.service --no-legend 2>/dev/null | grep -q '^gm-media-health.service'; then
  systemctl start gm-media-health.service
fi

if [[ "$state" == "passed" ]]; then
  printf 'PASS  %s\n' "$message"
  exit 0
fi
printf 'FAIL  %s\n' "$message" >&2
exit 1
