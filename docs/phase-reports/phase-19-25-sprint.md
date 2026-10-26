# Continuous editing-tool sprint

This report separates source implementation from live acceptance. The default editing model, recognition settings and story-first planner are preserved. No background hosted critique or automatic paid retries are enabled.

## Checkpoint 1: efficiency, evidence and navigation

Implemented:

- The worker gives each task class a turn instead of draining upload or ingest backlogs first. Visual backfill runs when foreground work is idle.
- Frame selection is capped before image extraction. Repeated text embeddings and the transcription model are cached. A shared process lock coordinates local inference; it does not unload resident model weights or promise GPU memory isolation.
- Exact-byte uploads can reuse derivatives only with matching analysis version/profile and verified artifact paths. An explicit refresh bypasses this cache.
- Recent worker stage timings are bounded and visible in Studio. They exclude queue wait and billing. A successful service installation records its source revision.
- Product aliases, source range annotations, complete-thought boundaries and local image OCR share an evidence vocabulary. Mentions remain distinct from verified pictured identity. Image OCR backfills through catalogue refresh without repeating transcription.
- Five primary navigation destinations expose related tools below. A per-tab media basket carries library selections into a job; source files and credentials are not stored in browser state.
- Library source details expose marked ranges. Studio exposes product-name management and processing times. Existing brand/effect forms receive accessibility fixes.
- Precise source trims, splits and replacement-take parameters use the existing deterministic revision path. Clip handles and a base-version precondition reject stale edits. Word timing shortcuts and restore-version API support preserve prior versions.

Verification at this checkpoint: 288 backend tests passed (five requiring FFmpeg skipped in the ordinary host run); an earlier 282-test run passed with actual FFmpeg renders. Eighteen browser component interaction checks and web TypeScript passed. All 29 migrations and actual source-knowledge SQL passed in isolated PostgreSQL. Further tools and final acceptance are still in progress.

## Acceptance still required

Deploy the completed sprint, then exercise the live suite and real footage. Playback judgement, GPU memory under load, user comprehension and multi-user pilot behaviour require live evidence. AI segmentation, automatic tracking and any other gated capability must remain labelled unavailable until its model, licence, latency and quality are verified.
