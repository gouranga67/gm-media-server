#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'Run this installer as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
configuration_file="/etc/gm-media-server/rclone/rclone.conf"

if [[ ! -r "$configuration_file" ]]; then
  printf 'Import the OneDrive connection before installing its backup timer.\n' >&2
  exit 1
fi
if [[ ! "$project_root" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  printf 'Unsafe project path: %s\n' "$project_root" >&2
  exit 1
fi

render_unit() {
  local source=$1
  local target=$2
  local rendered_directory rendered
  rendered_directory=$(mktemp --directory --tmpdir gm-media-systemd.XXXXXX)
  rendered="$rendered_directory/$(basename "$target")"
  sed "s|@PROJECT_ROOT@|$project_root|g" "$source" >"$rendered"
  systemd-analyze verify "$rendered"
  install -o root -g root -m 0644 "$rendered" "$target"
  rm -f -- "$rendered"
  rmdir -- "$rendered_directory"
}

docker compose --project-directory "$project_root" --profile tools config --quiet
render_unit \
  "$project_root/deploy/gm-media-offsite-backup.service" \
  /etc/systemd/system/gm-media-offsite-backup.service
render_unit \
  "$project_root/deploy/gm-media-offsite-backup.timer" \
  /etc/systemd/system/gm-media-offsite-backup.timer

systemctl daemon-reload
systemctl enable --now gm-media-offsite-backup.timer
printf 'Off-site backup timer installed. Starting the first encrypted upload now...\n'
systemctl start gm-media-offsite-backup.service
if systemctl list-unit-files gm-media-health.service --no-legend 2>/dev/null | grep -q '^gm-media-health.service'; then
  systemctl start gm-media-health.service
fi
systemctl --no-pager --full status gm-media-offsite-backup.service
systemctl list-timers --all gm-media-offsite-backup.timer --no-pager
