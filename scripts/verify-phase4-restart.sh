#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run this recovery drill as root: sudo %s [asset-id]\n' "$0" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

postgres_query() {
  local query="$1"
  docker compose exec -T -e GM_VERIFY_SQL="$query" postgres \
    sh -c 'exec psql --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --command "$GM_VERIFY_SQL"'
}

asset_id=${1:-}
if [[ -z "$asset_id" ]]; then
  asset_id=$(postgres_query \
    "SELECT ingest.asset_id FROM asset_ingests AS ingest JOIN assets AS asset ON asset.id = ingest.asset_id WHERE ingest.status = 'ready' AND asset.byte_size >= 100000 ORDER BY asset.created_at DESC LIMIT 1;" \
    | tr -d '[:space:]')
fi

if [[ ! "$asset_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  printf 'No suitable analyzed asset was found (received %q).\n' "$asset_id" >&2
  exit 1
fi

printf 'Requeueing analyzed asset %s for the recovery drill.\n' "$asset_id"
postgres_query \
  "UPDATE asset_ingests SET status = 'pending', attempts = 0, lease_expires_at = NULL, error = NULL, completed_at = NULL, updated_at = now() WHERE asset_id = '$asset_id';" \
  >/dev/null

printf 'Waiting for the worker to claim it...\n'
claimed=0
for _ in $(seq 1 100); do
  state=$(postgres_query "SELECT status FROM asset_ingests WHERE asset_id = '$asset_id';" | tr -d '[:space:]')
  if [[ "$state" == "running" ]]; then
    claimed=1
    break
  fi
  if [[ "$state" == "ready" || "$state" == "failed" ]]; then
    printf 'Analysis reached %s before it could be interrupted. Rerun the drill.\n' "$state" >&2
    exit 1
  fi
  sleep 0.1
done

if (( claimed == 0 )); then
  printf 'Worker did not claim the analysis within 10 seconds.\n' >&2
  exit 1
fi

printf 'Abruptly stopping the worker while the analysis is running...\n'
docker compose kill --signal KILL worker >/dev/null

printf 'Starting a replacement worker...\n'
docker compose up --detach --wait --wait-timeout 120 worker >/dev/null

printf 'Waiting for durable recovery and completion...\n'
for _ in $(seq 1 600); do
  record=$(postgres_query \
    "SELECT status || '|' || attempts::text FROM asset_ingests WHERE asset_id = '$asset_id';" \
    | tr -d '[:space:]')
  state=${record%%|*}
  attempts=${record##*|}
  if [[ "$state" == "ready" ]]; then
    if (( attempts < 2 )); then
      printf 'Analysis completed, but no interrupted attempt was recorded.\n' >&2
      exit 1
    fi
    printf 'PASS  Asset %s recovered after a forced worker stop and completed on attempt %s.\n' \
      "$asset_id" "$attempts"
    exit 0
  fi
  if [[ "$state" == "failed" ]]; then
    error=$(postgres_query "SELECT COALESCE(error, 'unknown error') FROM asset_ingests WHERE asset_id = '$asset_id';")
    printf 'Recovered analysis failed: %s\n' "$error" >&2
    exit 1
  fi
  sleep 1
done

printf 'Recovered analysis did not finish within 10 minutes.\n' >&2
exit 1
