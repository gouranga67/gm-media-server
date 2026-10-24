#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'The appliance health collector must run as root.\n' >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
status_directory=/var/lib/gm-media-server
status_file="$status_directory/appliance-health.json"
backup_status_file=/mnt/gm-backup/gm-media-backup-status.json
offsite_status_file=/var/lib/gm-media-server/offsite-backup-status.json
offsite_configuration_file=/etc/gm-media-server/rclone/rclone.conf
reboot_status_file=/var/lib/gm-media-server/reboot-recovery-drill.json
reboot_pending_file=/var/lib/gm-media-server/reboot-recovery-pending.json
lock_file=/run/lock/gm-media-health.lock

install -d -o root -g root -m 0755 "$status_directory"
exec 9>"$lock_file"
if ! flock --nonblock 9; then
  exit 0
fi

cd "$project_root"
disk_fields=$(df -B1 --output=size,avail,pcent /var/lib/docker 2>/dev/null | tail -n 1 | xargs || true)
read -r disk_total disk_available disk_percent <<<"$disk_fields"
disk_total=${disk_total:-0}
disk_available=${disk_available:-0}
disk_percent=${disk_percent%%%}
disk_percent=${disk_percent:-0}

gpu_temperature=null
if command -v nvidia-smi >/dev/null 2>&1; then
  measured_temperature=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d '[:space:]' || true)
  if [[ "$measured_temperature" =~ ^[0-9]+$ ]]; then
    gpu_temperature=$measured_temperature
  fi
fi

running_services=0
expected_services=7
if docker info >/dev/null 2>&1; then
  running_services=$(docker compose ps --services --status running 2>/dev/null | wc -l)
fi

queue_json='{}'
if docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
  queue_sql="SELECT json_build_object(
    'analysis_pending', (SELECT COUNT(*) FROM asset_ingests WHERE status IN ('pending', 'running')),
    'visual_pending', (SELECT COUNT(*) FROM asset_visual_indexes WHERE status IN ('pending', 'running')),
    'catalog_pending', (SELECT COUNT(*) FROM asset_catalogs WHERE status IN ('pending', 'running')),
    'edit_pending', (SELECT COUNT(*) FROM edit_runs WHERE status IN ('pending', 'planning', 'rendering')),
    'final_pending', ((SELECT COUNT(*) FROM final_exports WHERE status IN ('pending', 'rendering')) + (SELECT COUNT(*) FROM delivery_variants WHERE status IN ('pending', 'rendering'))),
    'failures_24h', ((SELECT COUNT(*) FROM edit_runs WHERE status = 'failed' AND updated_at >= now() - interval '24 hours') + (SELECT COUNT(*) FROM final_exports WHERE status = 'failed' AND updated_at >= now() - interval '24 hours') + (SELECT COUNT(*) FROM delivery_variants WHERE status = 'failed' AND updated_at >= now() - interval '24 hours'))
  );"
  queue_json=$(printf '%s\n' "$queue_sql" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' 2>/dev/null || printf '{}')
fi

smart_state=unavailable
if command -v smartctl >/dev/null 2>&1; then
  root_source=$(findmnt -nro SOURCE / 2>/dev/null || true)
  parent_device=$(lsblk -ndo PKNAME "$root_source" 2>/dev/null | head -n 1 || true)
  if [[ "$parent_device" =~ ^[A-Za-z0-9._-]+$ ]]; then
    smart_output=$(smartctl -H "/dev/$parent_device" 2>/dev/null || true)
    if grep -Eqi 'PASSED|OK' <<<"$smart_output"; then
      smart_state=passed
    elif [[ -n "$smart_output" ]]; then
      smart_state=attention
    fi
  fi
fi

temporary=$(mktemp --tmpdir gm-media-health.XXXXXX)
python3 - "$backup_status_file" "$offsite_status_file" "$offsite_configuration_file" "$reboot_status_file" "$reboot_pending_file" "$disk_total" "$disk_available" "$disk_percent" "$gpu_temperature" "$running_services" "$expected_services" "$smart_state" "$queue_json" >"$temporary" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

backup_path, offsite_path, offsite_config_path, reboot_path, reboot_pending_path, disk_total, disk_available, disk_percent, gpu_temp, running, expected, smart, queue_json = sys.argv[1:]
now = datetime.now(timezone.utc)
backup = {"state": "missing", "message": "No completed USB backup has been recorded.", "age_hours": None}
offsite = {
    "state": "not_configured",
    "message": "OneDrive recovery copy is not configured yet.",
    "age_hours": None,
    "configured": Path(offsite_config_path).is_file(),
}
reboot_recovery = {
    "status": "running" if Path(reboot_pending_path).is_file() else "not_run",
    "message": "The full-server reboot recovery drill has not passed yet.",
    "completed_at": None,
}
try:
    loaded = json.loads(Path(backup_path).read_text(encoding="utf-8"))
    backup.update(loaded)
    completed = loaded.get("completed_at")
    if completed:
        completed_at = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        age = max(0.0, (now - completed_at).total_seconds() / 3600)
        backup["age_hours"] = round(age, 1)
        if loaded.get("state") == "ready" and age > 30:
            backup["state"] = "stale"
            backup["message"] = "The newest successful backup is more than 30 hours old."
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    pass
if offsite["configured"]:
    offsite.update({"state": "missing", "message": "No completed OneDrive recovery copy has been recorded."})
    try:
        loaded = json.loads(Path(offsite_path).read_text(encoding="utf-8"))
        offsite.update(loaded)
        offsite["configured"] = True
        completed = loaded.get("completed_at")
        if completed:
            completed_at = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
            age = max(0.0, (now - completed_at).total_seconds() / 3600)
            offsite["age_hours"] = round(age, 1)
            if loaded.get("state") == "ready" and age > 36:
                offsite["state"] = "stale"
                offsite["message"] = "The newest verified OneDrive copy is more than 36 hours old."
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
if not Path(reboot_pending_path).is_file():
    try:
        reboot_recovery.update(json.loads(Path(reboot_path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
try:
    queues = json.loads(queue_json)
except json.JSONDecodeError:
    queues = {}

available = int(disk_available)
used_percent = int(disk_percent)
alerts: list[str] = []
if available < 50 * 1024**3 or used_percent >= 85:
    alerts.append("media disk space is below the safe operating threshold")
if backup.get("state") not in {"ready", "running"}:
    alerts.append("encrypted USB backup needs attention")
if offsite.get("state") not in {"ready", "running"}:
    alerts.append("encrypted OneDrive recovery copy needs attention")
if reboot_recovery.get("status") not in {"passed", "running"}:
    alerts.append("full-server reboot recovery drill has not passed")
if smart == "attention":
    alerts.append("SMART health needs attention")
if int(running) < int(expected):
    alerts.append("one or more application services are not running")
if int(queues.get("failures_24h", 0)) > 0:
    alerts.append("an edit or final export failed during the last 24 hours")

print(json.dumps({
    "generated_at": now.isoformat().replace("+00:00", "Z"),
    "status": "attention" if alerts else "healthy",
    "alerts": alerts,
    "disk": {"total_bytes": int(disk_total), "available_bytes": available, "used_percent": used_percent},
    "gpu": {"temperature_celsius": None if gpu_temp == "null" else int(gpu_temp)},
    "services": {"running": int(running), "expected": int(expected)},
    "queues": queues,
    "smart": {"state": smart},
    "backup": backup,
    "offsite_backup": offsite,
    "reboot_recovery": reboot_recovery,
}, indent=2))
PY
install -o root -g root -m 0644 "$temporary" "$status_file"
rm -f -- "$temporary"

