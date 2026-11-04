# Phase 29 — Durable library intake and bounded browsing

Source checkpoint: 2026-11-03. Deployment and real mixed-media intake acceptance pending.

## Result

Library → Add media now offers a destination folder, an optional numbered display name and a video role. Opening a folder preselects that destination. Registration saves these choices in the same database transaction as the original asset, before bytes transfer or analysis. A deleted destination rolls back registration; a retry with the same preferences returns the existing asset without replacing later owner edits or reopening a reviewed entry. This creates an upload-group project, never an editing job.

Two transfers run at a time, with a queue for up to 200 selected files per panel session. Pausing or failing releases a slot; resuming queues the existing transfer. Status checks group up to 100 uploaded originals per request, at ten-second intervals. Browser transfers still require the tab and device file. Once transfer finishes, server analysis and saved metadata no longer depend on the tab staying open.

The new Inbox is separate from Not in folders. Only new standalone imports enter it; old library assets and job uploads are not retrospectively marked unreviewed. It shows uploading, processing, ready and failed imports, including saved folders. Ready imports can be inspected, filed, sent to the existing explicit name/role suggestion flow, then marked reviewed. Filing does not silently mark reviewed. Dismiss is a separate confirmed action that clears the entry without cancelling a transfer or deleting an original. Failed analysis is displayed, not silently retried or charged to a hosted model.

The main library now requests 60 rows per page. SQL filters names, categories, media roles, favourites, folders and unfiled assets before pagination. Existing speech/visual search supplies up to 100 ranked asset matches; ordinary text search still spans library metadata. The bounded search result is reused when paging or changing filters, until the query or library revision changes. Reviewed duplicates collapse only when their canonical record also matches the current filters. A copy remains visible in a folder when its canonical record is outside that folder. Stable sort ties use asset IDs; changing page/filter clears selection so hidden files cannot be bulk-changed. Live changes to the library can shift offset pages; these are not frozen catalogue snapshots.

## Data and compatibility

Migration 044 adds `library_intakes` with immutable registration preferences and a review timestamp. Existing folder membership, metadata, originals, analysis and historical edit references retain their formats. Names are display metadata; original filenames and storage paths do not move. The older library API remains available to existing pickers and tools. This checkpoint paginates the main library, not every selector in the application.

`verify-phase29.py` reads the deployment capability, schema and bounded browse/Inbox responses. It starts no upload, render or model call. The live suite includes this readiness check. Technical checks do not establish usability on a real large library, upload recovery on every device, or subjective edit quality.

## Validation

- 681 backend tests passed, including nine new registration/review/conflict/schema cases and the existing CPU render tests.
- 79 interaction tests passed, including direct folder registration for mixed media, two-transfer queue/error/resume behaviour, grouped analysis polling, page selection isolation and explicit Inbox filing/review/dismissal.
- Eight source-suite gates passed, including TypeScript, interaction tests, public-release audit and production build.
- All 44 migrations and actual registration, browse, Inbox and grouped-status SQL executed in isolated PGlite. A 128-original fixture covered three disjoint pages, deterministic ties, canonical fallback, filtered evidence retrieval, archive isolation and clearing an entry without modifying the original.
- Phone and desktop browser checks use synthetic intercepted API responses; they do not mutate the production catalogue or upload private media.

## Acceptance and remaining scope

Follow the Phase 29 section of [testing-plan.md](../testing-plan.md). Start with a few videos, photos and audio files before trying a larger batch. Check the Inbox after leaving the uploading page once transfer is complete, apply reviewed name suggestions and verify originals remain available in old edits. The [folder suggestion follow-up](phase-29-folder-suggestions.md) now adds reviewable folder choices to auto-sort. The [nested-folder follow-up](phase-29-nested-folders.md) adds hierarchy, breadcrumbs and reviewed moves in migration 048. Indexing prioritisation, pagination of other media pickers and high-volume soak tests remain separate work. Hosted model defaults, editing rules and successful output quality are unchanged by this intake checkpoint.
