#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'The off-site backup must run as root.\n' >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mount_target="/mnt/gm-backup"
expected_uuid="a96d8bb5-d7b4-4fa7-bbea-2409417f9fbd"
repository="$mount_target/gm-media-restic"
configuration_file="/etc/gm-media-server/rclone/rclone.conf"
status_directory="/var/lib/gm-media-server"
status_file="$status_directory/offsite-backup-status.json"
lock_file="/run/lock/gm-media-backup.lock"
remote_root="gm-onedrive:GM Studio Backups/gm-server"

install -d -o root -g root -m 0755 "$status_directory"
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
history_stamp=$(date -u +%Y/%m/%d/%H%M%SZ)
stage=preflight
transfer_state=pending
verification_state=pending
retention_state=pending
verified_at=null

write_status() {
  local state=$1
  local message=$2
  local completed=${3:-null}
  local temporary
  temporary=$(mktemp "$status_directory/.offsite-status.XXXXXX")
  python3 - "$state" "$message" "$started_at" "$completed" "$stage" \
    "$transfer_state" "$verification_state" "$retention_state" "$verified_at" "$status_file" >"$temporary" <<'PY'
import json
import sys

state, message, started, completed, stage, transfer, verification, retention, verified, previous_path = sys.argv[1:]
try:
    from pathlib import Path
    previous = json.loads(Path(previous_path).read_text())
    if not isinstance(previous, dict):
        previous = {}
except (OSError, ValueError):
    previous = {}
last_verified = previous.get("last_verified_at") or (
    previous.get("completed_at") if previous.get("state") == "ready" else None
)
print(json.dumps({
    "state": state,
    "message": message,
    "started_at": started,
    "completed_at": None if completed == "null" else completed,
    "stage": stage,
    "stages": {"transfer": transfer, "verification": verification, "retention": retention},
    "verification_method": "one_way_file_size_comparison",
    "verified_at": None if verified == "null" else verified,
    "last_verified_at": last_verified if verified == "null" else verified,
}, indent=2))
PY
  chmod 0644 "$temporary"
  mv -f -- "$temporary" "$status_file"
}

offsite_failed() {
  local exit_code=$?
  trap - EXIT
  if (( exit_code == 0 )); then return; fi
  case "$stage" in
    transfer) transfer_state=failed ;;
    verification) verification_state=failed ;;
  esac
  write_status "failed" "Encrypted OneDrive backup failed during $stage with exit code $exit_code. See the service journal." "$(date -u +%Y-%m-%dT%H:%M:%SZ)" || true
  exit "$exit_code"
}
trap offsite_failed EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

write_status "running" "Checking prerequisites and waiting for local backup work to finish."
exec 9>"$lock_file"
if ! flock --wait 7200 9; then
  printf 'Timed out waiting for the local backup or restore drill to finish.\n' >&2
  exit 1
fi
mounted_uuid=$(findmnt -nro UUID --target "$mount_target" 2>/dev/null || true)
if [[ "$mounted_uuid" != "$expected_uuid" || ! -f "$repository/config" ]]; then
  printf 'The verified local backup repository is unavailable.\n' >&2
  exit 1
fi
if [[ ! -r "$configuration_file" ]]; then
  printf 'The OneDrive backup connection has not been imported.\n' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf 'Docker is unavailable.\n' >&2
  exit 1
fi
cd "$project_root"

source "$project_root/scripts/lib/offsite-backup.sh"
mirror_offsite_repository
