#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'Run this importer as root: sudo %s [transfer-file]\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
transfer_file=${1:-/tmp/gm-studio-rclone.conf}
configuration_directory="/etc/gm-media-server/rclone"
configuration_file="$configuration_directory/rclone.conf"
rollback_file=""

if [[ "$transfer_file" != /* || ! -f "$transfer_file" ]]; then
  printf 'The transferred rclone configuration must be an existing absolute file path.\n' >&2
  exit 1
fi

python3 - "$transfer_file" <<'PY'
import configparser
from pathlib import Path
import sys

path = Path(sys.argv[1])
parser = configparser.ConfigParser(interpolation=None)
try:
    parser.read_string(path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, configparser.Error) as error:
    raise SystemExit(f"invalid rclone configuration: {error}")
if set(parser.sections()) != {"gm-onedrive"}:
    raise SystemExit("the transfer file must contain only the gm-onedrive remote")
remote = parser["gm-onedrive"]
if remote.get("type") != "onedrive":
    raise SystemExit("gm-onedrive is not a OneDrive remote")
for required in ("token", "drive_id", "drive_type"):
    if not remote.get(required, "").strip():
        raise SystemExit(f"gm-onedrive is missing {required}")
PY

install -d -o root -g root -m 0700 "$configuration_directory"
if [[ -f "$configuration_file" ]]; then
  rollback_file=$(mktemp --tmpdir=/run gm-rclone-config.XXXXXX)
  install -o root -g root -m 0600 "$configuration_file" "$rollback_file"
fi
install -o root -g root -m 0600 "$transfer_file" "$configuration_file"

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ -n "$rollback_file" ]]; then
    install -o root -g root -m 0600 "$rollback_file" "$configuration_file"
  else
    rm -f -- "$configuration_file"
  fi
  printf 'OneDrive validation failed; the previous server configuration was restored.\n' >&2
  exit "$exit_code"
}
trap rollback ERR

cd "$project_root"
docker compose --profile tools run --rm offsite-sync mkdir "gm-onedrive:GM Studio Backups"
docker compose --profile tools run --rm offsite-sync lsd "gm-onedrive:GM Studio Backups" >/dev/null
trap - ERR
rm -f -- "$rollback_file"
rm -f -- "$transfer_file"

printf 'GM Studio imported and validated the OneDrive connection.\n'
printf 'The one-time transfer file was removed from %s.\n' "$transfer_file"
"$project_root/scripts/install-offsite-backup-service.sh"
