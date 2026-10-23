-- The first Phase 4 worker used a show_entries expression unavailable in
-- Ubuntu 22.04's FFprobe 4.4. Requeue only failed analyses once after moving
-- to the compatible show_streams/show_format interface.
UPDATE asset_ingests
SET status = 'pending',
    attempts = 0,
    error = NULL,
    lease_expires_at = NULL,
    started_at = NULL,
    completed_at = NULL,
    updated_at = now()
WHERE status = 'failed'
  AND error LIKE 'media command failed:%show_entries%Invalid argument%';
