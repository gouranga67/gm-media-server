#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'Run this recovery-key rotation as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mount_target="/mnt/gm-backup"
expected_uuid="a96d8bb5-d7b4-4fa7-bbea-2409417f9fbd"
repository="$mount_target/gm-media-restic"
configuration_directory="/etc/gm-media-server"
password_file="$configuration_directory/restic-password"
lock_file="/run/lock/gm-media-backup.lock"
old_password_copy=""
next_password_file=""
rotation_started=false

cleanup() {
  if [[ -n "$old_password_copy" ]]; then
    rm -f -- "$old_password_copy"
  fi
  if [[ -n "$next_password_file" && "$rotation_started" == false ]]; then
    rm -f -- "$next_password_file"
  fi
}
trap cleanup EXIT

exec 9>"$lock_file"
if ! flock --nonblock 9; then
  printf 'Recovery-key rotation cannot run while a GM Media backup or restore drill is active.\n' >&2
  exit 1
fi

mounted_uuid=$(findmnt -nro UUID --target "$mount_target" 2>/dev/null || true)
mounted_filesystem=$(findmnt -nro FSTYPE --target "$mount_target" 2>/dev/null || true)
mounted_options=$(findmnt -nro OPTIONS --target "$mount_target" 2>/dev/null || true)
if [[ "$mounted_uuid" != "$expected_uuid" || "$mounted_filesystem" != "ext4" ]]; then
  printf 'Refusing key rotation: %s is not the prepared backup USB (%s).\n' \
    "$mount_target" "$expected_uuid" >&2
  exit 1
fi
if [[ ",$mounted_options," != *,rw,* ]]; then
  printf 'Refusing key rotation: %s is read-only.\n' "$mount_target" >&2
  exit 1
fi
if [[ ! -f "$mount_target/.gm-backup-device" || ! -f "$repository/config" ]]; then
  printf 'Refusing key rotation: the prepared Restic repository was not found.\n' >&2
  exit 1
fi
if [[ ! -r "$password_file" ]]; then
  printf 'Refusing key rotation: the active root-only recovery key is missing.\n' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf 'Refusing key rotation: Docker is unavailable.\n' >&2
  exit 1
fi

umask 077
old_password_copy=$(mktemp --tmpdir=/run gm-restic-old-password.XXXXXX)
install -o root -g root -m 0600 "$password_file" "$old_password_copy"

# Keep the replacement on the same filesystem as the active key. If Restic
# succeeds but a later local step fails, this staged file remains available to
# root for recovery instead of leaving the repository inaccessible.
next_password_file=$(mktemp --tmpdir="$configuration_directory" .restic-password.next.XXXXXX)
openssl rand -base64 48 >"$next_password_file"
chown root:root "$next_password_file"
chmod 0600 "$next_password_file"

cd "$project_root"
printf 'Rotating the Restic repository password and validating the replacement...\n'
rotation_started=true
if ! docker compose --profile tools run --rm \
  --volume "$next_password_file:/run/secrets/gm-media-restic-password-new:ro" \
  backup key passwd \
    --new-password-file /run/secrets/gm-media-restic-password-new; then
  printf 'Restic did not complete the rotation. Keep this root-only staged key until the repository is checked: %s\n' \
    "$next_password_file" >&2
  exit 1
fi

if ! docker compose --profile tools run --rm \
  --volume "$next_password_file:/run/secrets/gm-media-restic-password-new:ro" \
  backup --password-file /run/secrets/gm-media-restic-password-new \
    snapshots --latest 1 >/dev/null; then
  printf 'The repository changed but replacement-key verification failed.\n' >&2
  printf 'Do not delete this root-only recovery file: %s\n' "$next_password_file" >&2
  exit 1
fi

# Atomic because both paths are in /etc/gm-media-server.
mv -f -- "$next_password_file" "$password_file"
next_password_file=""
rotation_started=false
chown root:root "$password_file"
chmod 0600 "$password_file"

printf 'Checking repository access through the installed replacement key...\n'
docker compose --profile tools run --rm backup snapshots --latest 1 >/dev/null
docker compose --profile tools run --rm backup check

if docker compose --profile tools run --rm \
  --volume "$old_password_copy:/run/secrets/gm-media-restic-password-old:ro" \
  backup --password-file /run/secrets/gm-media-restic-password-old \
    snapshots --latest 1 >/dev/null 2>&1; then
  printf 'Recovery-key rotation failed: the exposed password can still open the repository.\n' >&2
  exit 1
fi

printf '\nPASS  The exposed recovery key was revoked and the replacement key opens the repository.\n'
printf 'The replacement remains root-only at %s.\n' "$password_file"
printf 'Run sudo %s/scripts/show-backup-recovery-key.sh and save it directly in your password manager.\n' \
  "$project_root"
printf 'Do not paste the displayed replacement into chat, email, notes, or command output.\n'
