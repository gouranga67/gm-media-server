#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

if [[ ! -d .git ]]; then
  printf 'FAIL: run this check from a Git worktree.\n' >&2
  exit 1
fi

mapfile -d '' candidates < <(git ls-files --cached --others --exclude-standard -z)
if ((${#candidates[@]} == 0)); then
  printf 'FAIL: no release candidate files found.\n' >&2
  exit 1
fi

failures=0
fail() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

for required in README.md LICENSE NOTICE SECURITY.md CONTRIBUTING.md; do
  [[ -f "$required" ]] || fail "required public file is missing: $required"
done

for path in "${candidates[@]}"; do
  case "/$path" in
    */.env|*/.env.local|*/gm-studio-chatgpt.json)
      fail "private configuration is a release candidate: $path"
      ;;
  esac

  case "${path,,}" in
    *.pem|*.key|*.p12|*.pfx|*.mp4|*.mov|*.mkv|*.wav|*.mp3|*.m4a|*.aac|*.flac|*.webm|*.avi|*.heic|*.heif)
      fail "credential or private media file is a release candidate: $path"
      ;;
  esac
done

scan_files=()
for path in "${candidates[@]}"; do
  [[ "$path" == "scripts/check-public-release.sh" ]] || scan_files+=("$path")
done

if ((${#scan_files[@]} > 0)); then
  secret_pattern='(sk-[A-Za-z0-9_-]{20,}|oaiapp_[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)'
  machine_pattern='(/home/gm([/[:space:]]|$)|gm@gm-server|gm-server\.tail[0-9a-f]+\.ts\.net|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3})'
  tailnet_pattern='[A-Za-z0-9-]+\.tail[0-9a-f]+\.ts\.net'

  if rg --no-messages --line-number --regexp "$secret_pattern" -- "${scan_files[@]}"; then
    fail "a likely credential appears in the release candidate"
  fi
  if rg --no-messages --line-number --regexp "$machine_pattern" -- "${scan_files[@]}"; then
    fail "a deployment-specific path, host, or tailnet IP appears in the release candidate"
  fi
  if rg --no-messages --line-number --regexp "$tailnet_pattern" -- "${scan_files[@]}"; then
    fail "a real-looking tailnet DNS name appears in the release candidate"
  fi
fi

if ((failures > 0)); then
  printf '\nPublic release audit failed with %d finding(s).\n' "$failures" >&2
  exit 1
fi

printf 'PASS: %d release candidate files contain no recognized secrets, private media, or deployment identifiers.\n' "${#candidates[@]}"
