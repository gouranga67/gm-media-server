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
status_directory=/var/lib/gm-media-server
restore_state=failed
original_count=0
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
write_restore_status() {
  local result=$1
  install -d -o root -g root -m 0755 "$status_directory"
  python3 - "$status_directory" "$result" "$original_count" "$started_at" <<'PY'
import json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
directory,state,count,started = sys.argv[1:]
document = dict(version=1,status=state,original_count=int(count),started_at=started,
    completed_at=datetime.now(timezone.utc).isoformat() if state != 'running' else None,
    method='isolated file restore and database-dump listing')
fd,name = tempfile.mkstemp(prefix='.restore-status-',dir=directory)
try:
    with os.fdopen(fd,'w') as stream:
        json.dump(document,stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.chmod(name,0o644)
    os.replace(name,Path(directory)/'restore-verification.json')
finally:
    if os.path.exists(name): os.unlink(name)
PY
}
cleanup() {
  case "$restore_root" in
    /tmp/gm-media-restore.*) rm -rf -- "$restore_root" ;;
    *) printf 'Refusing unsafe temporary cleanup path: %s\n' "$restore_root" >&2 ;;
  esac
}
finish() {
  local result=$?
  trap - EXIT
  if (( result != 0 )); then restore_state=failed; fi
  write_restore_status "$restore_state" || printf 'Could not save restore verification status.\n' >&2
  cleanup || true
  exit "$result"
}
trap finish EXIT
write_restore_status running

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

restore_state=passed
printf 'PASS  The database dump listing is readable and %d original media files were recovered in isolation.\n' \
  "$original_count"

