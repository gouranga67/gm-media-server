#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this restore drill as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
lock_file="/run/lock/gm-media-backup.lock"

exec 9>"$lock_file"
if ! flock --nonblock 9; then
  printf 'Restore drill cannot start while a GM Media backup is running. Try again when the backup finishes.\n' >&2
  exit 1
fi

restore_root=$(mktemp --directory --tmpdir gm-media-restore.XXXXXX)
cleanup() {
  case "$restore_root" in
    /tmp/gm-media-restore.*) rm -rf -- "$restore_root" ;;
    *) printf 'Refusing unsafe temporary cleanup path: %s\n' "$restore_root" >&2 ;;
  esac
}
trap cleanup EXIT

cd "$project_root"
printf 'Restoring the latest database dump into an isolated temporary directory...\n'
docker compose --profile tools run --rm \
  --volume "$restore_root:/restore" \
  restore restore --no-lock latest --tag database --target /restore

database_dump="$restore_root/database/gm-media.dump"
if [[ ! -s "$database_dump" ]]; then
  printf 'Restore drill failed: database dump was not restored.\n' >&2
  exit 1
fi
docker compose exec -T postgres pg_restore --list <"$database_dump" >/dev/null

printf 'Restoring one full snapshot into the isolated directory...\n'
docker compose --profile tools run --rm \
  --volume "$restore_root:/restore" \
  restore restore --no-lock latest --tag full --target /restore

if [[ ! -d "$restore_root/source/media/originals" ]]; then
  printf 'Restore drill failed: the originals directory was not restored.\n' >&2
  exit 1
fi
original_count=$(find "$restore_root/source/media/originals" -type f | wc -l)
if (( original_count < 1 )); then
  printf 'Restore drill failed: no original media files were restored.\n' >&2
  exit 1
fi

printf 'PASS  Restored database dump is valid and %d original media files were recovered in isolation.\n' \
  "$original_count"

