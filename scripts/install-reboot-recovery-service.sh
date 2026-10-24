#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this installer as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_unit="$project_root/deploy/gm-media-reboot-recovery.service"
target_unit=/etc/systemd/system/gm-media-reboot-recovery.service

if [[ ! "$project_root" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  printf 'Unsafe project path: %s\n' "$project_root" >&2
  exit 1
fi

rendered_directory=$(mktemp --directory --tmpdir gm-media-reboot-unit.XXXXXX)
rendered="$rendered_directory/gm-media-reboot-recovery.service"
cleanup() {
  rm -f -- "$rendered"
  rmdir -- "$rendered_directory"
}
trap cleanup EXIT
sed "s|@PROJECT_ROOT@|$project_root|g" "$source_unit" >"$rendered"
systemd-analyze verify "$rendered"
install -o root -g root -m 0644 "$rendered" "$target_unit"
systemctl daemon-reload
systemctl enable gm-media-reboot-recovery.service
printf 'Reboot recovery verifier installed.\n'
