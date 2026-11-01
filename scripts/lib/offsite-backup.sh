#!/usr/bin/env bash
# Sourced by the root-only runner. Keep the remote operations separate so they
# can be exercised with a fake transport without touching a backup repository.

mirror_offsite_repository() {
  stage=transfer
  transfer_state=running
  write_status running 'Uploading the encrypted OneDrive recovery copy.'
  printf 'Mirroring the encrypted Restic repository to OneDrive...\n'
  docker compose --profile tools run --rm offsite-sync sync \
    /source "$remote_root/restic-current" \
    --backup-dir "$remote_root/restic-history/$history_stamp" \
    --check-first --create-empty-src-dirs --transfers 4 --checkers 8 \
    --retries 5 --low-level-retries 10 --max-delete 10000 \
    --stats 30s --stats-one-line
  transfer_state=ready

  stage=verification
  verification_state=running
  write_status running 'Upload complete; comparing local and OneDrive file sizes.'
  printf 'Comparing local and off-site repository file sizes...\n'
  docker compose --profile tools run --rm offsite-sync check \
    /source "$remote_root/restic-current" --one-way --size-only --checkers 8
  verification_state=ready
  verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  stage=retention
  retention_state=running
  write_status running 'File-size comparison passed; maintaining old OneDrive history.'
  printf 'Removing displaced remote history older than 90 days...\n'
  # Restic objects keep their original modification times when displaced. Age
  # filtering alone could therefore delete a newly displaced old object. Also
  # protect all UTC date buckets from the most recent 90 days (inclusive).
  local recent_history_days day
  local -a retention_filters=()
  recent_history_days=$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
today = datetime.now(timezone.utc).date()
for offset in range(91):
    print((today - timedelta(days=offset)).strftime("%Y/%m/%d"))
PY
  )
  while IFS= read -r day; do
    retention_filters+=(--exclude "/$day/**")
  done <<< "$recent_history_days"
  # This path contains displaced encrypted history, never the current mirror.
  # Do not combine filtered file deletion with --rmdirs: retained young files
  # can make OneDrive directory removal fail. Empty directories use no media
  # storage and can safely remain. A missing history root is normal initially.
  if docker compose --profile tools run --rm offsite-sync mkdir "$remote_root/restic-history" &&
     docker compose --profile tools run --rm offsite-sync delete \
       "$remote_root/restic-history" --min-age 90d "${retention_filters[@]}"; then
    retention_state=ready
    stage=complete
    write_status ready 'Encrypted OneDrive copy uploaded; file-size comparison and history maintenance passed.' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'PASS  Encrypted OneDrive copy uploaded and file sizes matched; this is not a restore drill.\n'
  else
    retention_state=failed
    write_status attention 'OneDrive copy uploaded and file sizes matched; old-history maintenance needs attention.' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'WARN  Current OneDrive copy matched; old-history maintenance failed. See the service journal.\n' >&2
  fi
}
