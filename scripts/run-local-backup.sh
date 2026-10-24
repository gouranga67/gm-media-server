#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'The backup must run as root.\n' >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mount_target="/mnt/gm-backup"
repository="$mount_target/gm-media-restic"
status_file="$mount_target/gm-media-backup-status.json"
expected_uuid="a96d8bb5-d7b4-4fa7-bbea-2409417f9fbd"
lock_file="/run/lock/gm-media-backup.lock"

exec 9>"$lock_file"
if ! flock --nonblock 9; then
  printf 'Another GM Media backup is already running.\n' >&2
  exit 1
fi

mounted_uuid=$(findmnt -nro UUID --target "$mount_target" 2>/dev/null || true)
mounted_options=$(findmnt -nro OPTIONS --target "$mount_target" 2>/dev/null || true)
if [[ "$mounted_uuid" != "$expected_uuid" || ",$mounted_options," != *,rw,* ]]; then
  printf 'Prepared backup USB is absent or read-only.\n' >&2
  exit 1
fi
if [[ ! -r /etc/gm-media-server/restic-password ]]; then
  printf 'Restic password is not installed.\n' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf 'Docker is unavailable.\n' >&2
  exit 1
fi

cd "$project_root"
backup_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)

write_status() {
  local state=$1
  local message=$2
  local completed=${3:-null}
  local status_temporary
  status_temporary=$(mktemp --tmpdir gm-media-backup-status.XXXXXX)
  python3 - "$state" "$message" "$backup_started" "$completed" >"$status_temporary" <<'PY'
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
  install -o root -g gm -m 0640 "$status_temporary" "$status_file"
  rm -f -- "$status_temporary"
}

backup_failed() {
  local exit_code=$?
  trap - ERR
  write_status "failed" "Backup command failed with exit code $exit_code." "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit "$exit_code"
}
trap backup_failed ERR

write_status "running" "Encrypted local backup is running."

if [[ ! -f "$repository/config" ]]; then
  docker compose --profile tools run --rm backup init
fi

printf 'Backing up a consistent PostgreSQL dump...\n'
docker compose exec -T postgres \
  sh -c 'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
  | docker compose --profile tools run --rm -T backup \
      backup --stdin --stdin-filename /database/gm-media.dump \
      --tag database --tag gm-media

printf 'Backing up media, protected credentials, and application configuration...\n'
docker compose --profile tools run --rm backup backup \
  /source/media /source/auth /source/project \
  --exclude /source/project/.git \
  --exclude /source/project/node_modules \
  --exclude /source/project/apps/web/.next \
  --exclude-caches \
  --tag full --tag gm-media

printf 'Applying retention policy...\n'
docker compose --profile tools run --rm backup forget \
  --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune

printf 'Checking repository structure and a sample of stored data...\n'
docker compose --profile tools run --rm backup check --read-data-subset=5%

completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
write_status "ready" "Encrypted local backup completed and passed repository checks." "$completed_at"
docker compose --profile tools run --rm backup snapshots --latest 4
df -h "$mount_target"

