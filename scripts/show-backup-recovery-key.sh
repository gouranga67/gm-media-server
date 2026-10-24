#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

password_file="/etc/gm-media-server/restic-password"
if [[ ! -r "$password_file" ]]; then
  printf 'The backup recovery key has not been created yet.\n' >&2
  exit 1
fi

printf 'Save this key in a password manager. Do not send it through chat or email.\n\n'
sed -n '1p' "$password_file"

