#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this installer as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mount_target="/mnt/gm-backup"
expected_uuid="a96d8bb5-d7b4-4fa7-bbea-2409417f9fbd"
configuration_directory="/etc/gm-media-server"
password_file="$configuration_directory/restic-password"

if [[ ! "$project_root" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  printf 'Unsafe project path: %s\n' "$project_root" >&2
  exit 1
fi

mounted_uuid=$(findmnt -nro UUID --target "$mount_target" 2>/dev/null || true)
mounted_filesystem=$(findmnt -nro FSTYPE --target "$mount_target" 2>/dev/null || true)
mounted_options=$(findmnt -nro OPTIONS --target "$mount_target" 2>/dev/null || true)
if [[ "$mounted_uuid" != "$expected_uuid" || "$mounted_filesystem" != "ext4" ]]; then
  printf 'Refusing backup setup: %s is not the prepared ext4 USB (%s).\n' \
    "$mount_target" "$expected_uuid" >&2
  exit 1
fi
if [[ ",$mounted_options," != *,rw,* ]]; then
  printf 'Refusing backup setup: %s is not writable.\n' "$mount_target" >&2
  exit 1
fi
if [[ ! -f "$mount_target/.gm-backup-device" ]]; then
  printf 'Refusing backup setup: the GM backup marker is missing.\n' >&2
  exit 1
fi

install -d -o root -g root -m 0700 "$configuration_directory"
if [[ ! -f "$password_file" ]]; then
  password_temporary=$(mktemp --tmpdir gm-restic-password.XXXXXX)
  cleanup_password() {
    rm -f -- "$password_temporary"
  }
  trap cleanup_password EXIT
  openssl rand -base64 48 >"$password_temporary"
  install -o root -g root -m 0600 "$password_temporary" "$password_file"
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

render_unit \
  "$project_root/deploy/gm-media-backup.service" \
  /etc/systemd/system/gm-media-backup.service
render_unit \
  "$project_root/deploy/gm-media-backup.timer" \
  /etc/systemd/system/gm-media-backup.timer
render_unit \
  "$project_root/deploy/gm-media-health.service" \
  /etc/systemd/system/gm-media-health.service
render_unit \
  "$project_root/deploy/gm-media-health.timer" \
  /etc/systemd/system/gm-media-health.timer

docker compose --project-directory "$project_root" --profile tools config --quiet
systemctl daemon-reload
systemctl enable --now gm-media-backup.timer
systemctl enable --now gm-media-health.timer

printf 'Backup service installed. Starting the first encrypted backup now...\n'
systemctl start gm-media-backup.service
systemctl start gm-media-health.service
systemctl --no-pager --full status gm-media-backup.service
systemctl list-timers --all gm-media-backup.timer gm-media-health.timer --no-pager

printf '\nThe Restic recovery key is stored root-only at %s.\n' "$password_file"
printf 'Run sudo %s/scripts/show-backup-recovery-key.sh and save it in your password manager.\n' \
  "$project_root"

