#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'Run this private-access setup as root: sudo %s\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
environment_file="$project_root/.env"

if [[ ! -f "$environment_file" ]]; then
  printf 'Private-access setup cannot find %s.\n' "$environment_file" >&2
  exit 1
fi
if ! tailscale status --json >/dev/null 2>&1; then
  printf 'Tailscale is not connected; private access was not changed.\n' >&2
  exit 1
fi

tailscale_status=$(tailscale status --json)
readarray -t identity < <(python3 -c '
import json, sys

document = json.load(sys.stdin)
self_node = document.get("Self") or {}
user_id = str(self_node.get("UserID") or "")
user = (document.get("User") or {}).get(user_id) or {}
login = str(user.get("LoginName") or "").strip()
dns_name = str(self_node.get("DNSName") or "").strip().rstrip(".")
if not login or not dns_name:
    raise SystemExit("the Tailscale owner identity or DNS name is unavailable")
print(login)
print(dns_name)
' <<<"$tailscale_status")

allowed_login=${identity[0]:-}
tailscale_dns_name=${identity[1]:-}
if [[ -z "$allowed_login" || -z "$tailscale_dns_name" ]]; then
  printf 'Could not determine the Tailscale owner identity.\n' >&2
  exit 1
fi

python3 - "$environment_file" "$allowed_login" "$tailscale_dns_name" <<'PY'
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
login = sys.argv[2]
dns_name = sys.argv[3]
updates = {
    "APP_ORIGIN": f"https://{dns_name}",
    "TAILSCALE_AUTH_REQUIRED": "true",
    "TAILSCALE_ALLOWED_LOGIN": login,
}

original = path.read_text(encoding="utf-8").splitlines()
seen: set[str] = set()
rendered: list[str] = []
for line in original:
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
    if key in updates:
        rendered.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        rendered.append(line)
for key, value in updates.items():
    if key not in seen:
        rendered.append(f"{key}={value}")

metadata = path.stat()
descriptor, temporary_name = tempfile.mkstemp(prefix=".env.private-access.", dir=path.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(rendered) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(temporary_name, metadata.st_uid, metadata.st_gid)
    os.chmod(temporary_name, metadata.st_mode & 0o777)
    os.replace(temporary_name, path)
finally:
    if os.path.exists(temporary_name):
        os.unlink(temporary_name)
PY

printf 'Rebuilding GM Studio with Tailscale identity enforcement...\n'
"$project_root/scripts/install-service.sh"
tailscale serve --bg --yes http://127.0.0.1:3000

health_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --max-time 10 http://127.0.0.1:3000/api/health)
unauthenticated_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --max-time 10 http://127.0.0.1:3000/)
authenticated_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --max-time 10 --header "Tailscale-User-Login: $allowed_login" http://127.0.0.1:3000/)
serve_status=$(tailscale serve status)

if [[ "$health_status" != "200" || "$unauthenticated_status" != "401" || "$authenticated_status" != "200" ]]; then
  printf 'Private-access verification failed (health=%s direct=%s identity=%s).\n' \
    "$health_status" "$unauthenticated_status" "$authenticated_status" >&2
  exit 1
fi
if [[ "$serve_status" != *"(tailnet only)"* || "$serve_status" == *"Funnel on"* ]]; then
  printf 'Tailscale Serve is not confirmed private; inspect `tailscale serve status`.\n' >&2
  exit 1
fi

printf 'PASS  GM Studio accepts the configured Tailscale owner and rejects direct unauthenticated requests.\n'
printf 'Private URL: https://%s\n' "$tailscale_dns_name"
