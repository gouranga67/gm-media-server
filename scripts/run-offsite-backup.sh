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

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
history_stamp=$(date -u +%Y/%m/%d/%H%M%SZ)

write_status() {
  local state=$1
  local message=$2
  local completed=${3:-null}
  local temporary
  temporary=$(mktemp --tmpdir gm-media-offsite-status.XXXXXX)
  python3 - "$state" "$message" "$started_at" "$completed" >"$temporary" <<'PY'
import json
import sys

state, message, started, completed = sys.argv[1:]
print(json.dumps({
    "state": state,
    "message": message,
    "started_at": started,
    "completed_at": None if completed == "null" else completed,
}, indent=2))
PY
  install -o root -g root -m 0644 "$temporary" "$status_file"
  rm -f -- "$temporary"
}

offsite_failed() {
  local exit_code=$?
  trap - ERR
  write_status "failed" "Encrypted OneDrive backup failed with exit code $exit_code." "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit "$exit_code"
}
trap offsite_failed ERR

write_status "running" "Encrypted OneDrive backup is running."
cd "$project_root"

printf 'Mirroring the encrypted Restic repository to OneDrive...\n'
docker compose --profile tools run --rm offsite-sync sync \
  /source "$remote_root/restic-current" \
  --backup-dir "$remote_root/restic-history/$history_stamp" \
  --check-first \
  --create-empty-src-dirs \
  --transfers 4 \
  --checkers 8 \
  --retries 5 \
  --low-level-retries 10 \
  --max-delete 10000 \
  --stats 30s \
  --stats-one-line

printf 'Comparing local and off-site repository file sizes...\n'
docker compose --profile tools run --rm offsite-sync check \
  /source "$remote_root/restic-current" \
  --one-way \
  --size-only \
  --checkers 8

printf 'Removing displaced remote history older than 90 days...\n'
# A clean first upload has no displaced files, so rclone has not created the
# history root yet.  `delete` treats that normal state as exit code 3.  Create
# the empty root first; --rmdirs removes children but deliberately leaves the
# supplied root in place for later runs.
docker compose --profile tools run --rm offsite-sync mkdir \
  "$remote_root/restic-history"
docker compose --profile tools run --rm offsite-sync delete \
  "$remote_root/restic-history" \
  --min-age 90d \
  --rmdirs

completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
write_status "ready" "Encrypted OneDrive backup completed and matched the local repository." "$completed_at"
printf 'PASS  The encrypted repository is present and verified off-site.\n'
