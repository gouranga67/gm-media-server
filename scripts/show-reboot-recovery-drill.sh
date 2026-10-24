#!/usr/bin/env bash
set -euo pipefail

result_file=/var/lib/gm-media-server/reboot-recovery-drill.json
pending_file=/var/lib/gm-media-server/reboot-recovery-pending.json

if [[ -f "$result_file" ]]; then
  cat "$result_file"
  exit 0
fi
if [[ -f "$pending_file" ]]; then
  printf 'The reboot recovery drill is still running.\n'
  exit 2
fi
printf 'No reboot recovery drill result has been recorded yet.\n' >&2
exit 1
