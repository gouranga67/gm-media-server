#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this installer as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
unit_source="$project_root/deploy/gm-media-server.service"
unit_target=/etc/systemd/system/gm-media-server.service

if [[ ! "$project_root" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  printf 'The project path contains characters that cannot be safely written to the systemd unit: %s\n' "$project_root" >&2
  exit 1
fi

install -d -o root -g root -m 0755 /var/lib/gm-media-server

docker compose --project-directory "$project_root" config --quiet
unit_rendered_dir=$(mktemp --directory --tmpdir gm-media-server-systemd.XXXXXX)
unit_rendered="$unit_rendered_dir/gm-media-server.service"
cleanup() {
  rm -f -- "$unit_rendered"
  rmdir -- "$unit_rendered_dir"
}
trap cleanup EXIT
sed "s|@PROJECT_ROOT@|$project_root|g" "$unit_source" >"$unit_rendered"
systemd-analyze verify "$unit_rendered"
install -o root -g root -m 0644 "$unit_rendered" "$unit_target"
systemctl daemon-reload
systemctl enable gm-media-server.service
systemctl restart gm-media-server.service
systemctl --no-pager --full status gm-media-server.service
deployed_commit=$(git -C "$project_root" rev-parse HEAD 2>/dev/null || printf unknown)
printf '{"commit":"%s"}\n' "$deployed_commit" > /var/lib/gm-media-server/build.json.tmp
chmod 0644 /var/lib/gm-media-server/build.json.tmp
mv /var/lib/gm-media-server/build.json.tmp /var/lib/gm-media-server/build.json
