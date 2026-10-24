#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
  printf 'Run the reboot drill as root: sudo %s --confirm-reboot\n' "$0" >&2
  exit 1
fi
if [[ ${1:-} != "--confirm-reboot" ]]; then
  printf 'This drill deliberately reboots the server. Run it again with --confirm-reboot when ready.\n' >&2
  exit 2
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
status_directory=/var/lib/gm-media-server
pending_file="$status_directory/reboot-recovery-pending.json"
result_file="$status_directory/reboot-recovery-drill.json"
lock_file=/run/lock/gm-media-reboot-drill.lock

install -d -o root -g root -m 0755 "$status_directory"
exec 9>"$lock_file"
if ! flock --nonblock 9; then
  printf 'Another reboot recovery drill is already being prepared.\n' >&2
  exit 1
fi
if [[ -f "$pending_file" ]]; then
  printf 'A previous reboot drill is still pending. Inspect it before starting another.\n' >&2
  exit 1
fi

cd "$project_root"
docker compose ps --status running postgres worker >/dev/null
active_count=$(docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT (SELECT count(*) FROM edit_runs WHERE status IN ('"'"'pending'"'"','"'"'planning'"'"','"'"'rendering'"'"')) + (SELECT count(*) FROM final_exports WHERE status IN ('"'"'pending'"'"','"'"'rendering'"'"'));"')
if [[ ! "$active_count" =~ ^[0-9]+$ || "$active_count" != "0" ]]; then
  printf 'The editing queues are not idle (%s active item(s)); wait for them before rebooting.\n' "$active_count" >&2
  exit 1
fi

"$project_root/scripts/install-reboot-recovery-service.sh"

selection_sql=$(cat <<'SQL'
WITH candidate AS (
  SELECT er.id AS source_run_id, er.job_id AS source_job_id,
         ep.schema_version, ep.document, ep.provider, ep.model, ep.document_sha256,
         j.recipe, j.target_duration_seconds, j.edit_style, j.music_mode,
         j.target_platform, j.must_include, j.editor_model,
         j.reasoning_effort, j.output_aspect
  FROM edit_runs er
  JOIN jobs j ON j.id = er.job_id
  JOIN edit_plans ep ON ep.id = er.edit_plan_id
  WHERE er.status = 'ready'
    AND er.edit_plan_id IS NOT NULL
  ORDER BY (j.recipe = 'montage') DESC, er.completed_at DESC NULLS LAST
  LIMIT 1
), project_insert AS (
  INSERT INTO projects (name, brief, privacy_mode, ai_copy_allowed)
  SELECT 'Phase 7 verification — reboot recovery ' || to_char(clock_timestamp(), 'YYYYMMDDHH24MISS'),
         'Automated full-machine render recovery drill. Safe to ignore in editing history.',
         'local_only', false
  FROM candidate
  RETURNING id
), job_insert AS (
  INSERT INTO jobs (
    project_id, recipe, status, target_duration_seconds, edit_style,
    music_mode, target_platform, must_include, editor_model,
    reasoning_effort, output_aspect
  )
  SELECT project_insert.id, candidate.recipe, 'previewing',
         candidate.target_duration_seconds, candidate.edit_style,
         candidate.music_mode, candidate.target_platform, candidate.must_include,
         candidate.editor_model, candidate.reasoning_effort, candidate.output_aspect
  FROM project_insert CROSS JOIN candidate
  RETURNING id
), asset_insert AS (
  INSERT INTO job_assets (job_id, asset_id)
  SELECT job_insert.id, source_assets.asset_id
  FROM job_insert CROSS JOIN candidate
  JOIN job_assets source_assets ON source_assets.job_id = candidate.source_job_id
  RETURNING asset_id
), plan_insert AS (
  INSERT INTO edit_plans (
    job_id, version, schema_version, document, provider, model, document_sha256
  )
  SELECT job_insert.id, 1, candidate.schema_version, candidate.document,
         candidate.provider, candidate.model, candidate.document_sha256
  FROM job_insert CROSS JOIN candidate
  WHERE EXISTS (SELECT 1 FROM asset_insert)
  RETURNING id, job_id
), run_insert AS (
  INSERT INTO edit_runs (
    job_id, version, status, edit_plan_id, provider, model,
    reasoning_effort
  )
  SELECT plan_insert.job_id, 1, 'pending', plan_insert.id,
         candidate.provider, candidate.model, candidate.reasoning_effort
  FROM plan_insert CROSS JOIN candidate
  RETURNING id, job_id, version
), event_insert AS (
  INSERT INTO job_events (job_id, event_type, payload)
  SELECT job_id, 'reboot_recovery_drill_requested',
         jsonb_build_object('run_id', id, 'version', version)
  FROM run_insert
)
SELECT run_insert.id::text || '|' || run_insert.job_id::text || '|' || run_insert.version::text || '|' || candidate.source_run_id::text
FROM run_insert CROSS JOIN candidate;
SQL
)
selection=$(printf '%s\n' "$selection_sql" | docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At')
if [[ -z "$selection" ]]; then
  printf 'No completed edit with a reusable plan was found. Complete one preview before running the drill.\n' >&2
  exit 1
fi
IFS='|' read -r run_id job_id version based_on_run_id <<<"$selection"
uuid_pattern='^[0-9a-fA-F-]{36}$'
if [[ ! "$run_id" =~ $uuid_pattern || ! "$job_id" =~ $uuid_pattern || ! "$based_on_run_id" =~ $uuid_pattern || ! "$version" =~ ^[0-9]+$ ]]; then
  printf 'The database returned an invalid recovery-drill record.\n' >&2
  exit 1
fi

boot_id=$(cat /proc/sys/kernel/random/boot_id)
temporary=$(mktemp --tmpdir gm-reboot-pending.XXXXXX)
python3 - "$run_id" "$job_id" "$version" "$based_on_run_id" "$boot_id" >"$temporary" <<'PY'
import json
import sys
from datetime import datetime, timezone

run_id, job_id, version, based_on, boot_id = sys.argv[1:]
print(json.dumps({
    "state": "waiting_for_reboot",
    "run_id": run_id,
    "job_id": job_id,
    "version": int(version),
    "based_on_run_id": based_on,
    "boot_id_before": boot_id,
    "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}, indent=2))
PY
install -o root -g root -m 0600 "$temporary" "$pending_file"
rm -f -- "$temporary" "$result_file"

printf 'Waiting for the worker to enter the render stage...\n'
deadline=$((SECONDS + 300))
while (( SECONDS < deadline )); do
  run_status=$(docker compose exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"SELECT status FROM edit_runs WHERE id = '$run_id';\"")
  if [[ "$run_status" == "rendering" ]]; then
    printf 'Render is active. Persisting the drill state and rebooting now...\n'
    sync
    systemctl reboot
    exit 0
  fi
  if [[ "$run_status" == "failed" || "$run_status" == "ready" ]]; then
    rm -f -- "$pending_file"
    printf 'The drill run reached %s before it could be interrupted; no reboot was performed.\n' "$run_status" >&2
    exit 1
  fi
  sleep 0.2
done
rm -f -- "$pending_file"
printf 'The worker did not enter rendering within five minutes; no reboot was performed.\n' >&2
exit 1
