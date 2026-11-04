# Phase 29 — Paged source selection in Create

Source checkpoint: 2026-11-04. Deployment and owner mixed-media acceptance pending.

## Result

Create → New edit previously fetched only the newest 500 library originals, then filtered that local list. Older footage could be absent even when it was ready in Library. The picker now uses the existing server-side library browser in pages of 60. Media kind, footage role, project, direct folder membership and metadata/search evidence filter candidates before paging. A folder selector shows full nested paths and includes Not in folders. Choosing a folder shows its direct media, matching Library; it does not recursively include descendants.

Selections are separate from the current page. They survive paging, searches and folder/type/project/role changes. An expandable selected-originals list shows names and explicit Remove/Clear controls. It still combines with new device uploads in one job. Merely browsing or selecting does not create a project or edit. The existing project creation, source attachment, analysis, explicit Start editing and approval flow remain in place.

Selections carried over from Library are loaded by their exact IDs, rather than requiring them to occur in a recent page. These lookups read at most 100 records each and preserve the requested original, including an explicitly selected noncanonical duplicate. Unavailable, archived, unfinished or unhashed selections are not silently dropped or substituted: the form blocks creation and offers removal or refresh. Lookup failures retain the selection for retry. The existing attachment API rechecks source availability when attaching.

The server attachment contract permits 100 originals in one request. The form now exposes that limit before project creation, disables additional unselected rows at 100 and requires explicit reduction of a larger carried-over basket. The per-tab basket can still retain up to 500 IDs from Library; it is not permission to attach all 500 to one job. New device uploads remain separately listed.

## Compute, data and limits

The bounded browser endpoint adds optional editing-ready, media-kind and project filters. Defaults for other library clients retain their existing behaviour. Editing-ready rows require active ready originals, ready ingest, known checksum, media type and byte size. The exact-selection and project-choice endpoints return display metadata, not storage paths, originals or full analysis. No migration, hosted model request, source reanalysis or new editing default is introduced.

Speech/visual search still supplies up to 100 ranked source matches. Paging and changing folder/role reuse the settled search response; query, media-kind, project or explicit refresh can rerun that local search. Whole-library metadata matching remains available. A folder filter can narrow the bounded evidence results, so this is not exhaustive semantic retrieval of every matching scene. Offset pages can shift when the live library changes. Folder and project option lists remain unpaginated metadata lists. Large production-library throughput and real upload recovery still require owner acceptance; fixture counts are not speed measurements.

Stale page/search responses cannot replace a newer filter, and a failed page leaves the selected-originals list available. Refresh retries the current page. The search input follows the API's 160-character limit. Browser session storage retains selected IDs; it does not save files or unfinished upload bytes.

## Verification

- Backend: 773 tests run, 772 passed; one unrelated disposable rclone retention integration skipped because rclone was unavailable. Five new tests cover bound SQL filters, page-only hydration, exact selections, metadata-only project choices and HTTP limits.
- UI: all 109 interaction tests passed, including six new cases for 620-source browsing, old basket selections, folder paths, search reuse, failure retry, late responses, unavailable selections and the 100-original guard. The existing mixed server/device creation and explicit edit-start test also passed.
- All eight source-suite gates passed, including TypeScript, the production build and public-release audit.
- Isolated PostgreSQL-compatible execution applied all 49 migrations and exercised the actual browse, selection, project and hydration queries with 620 ready originals across 11 pages. It verified exact selection beyond the first 500, exclusion of archived/unfinished/unhashed records and folder-local duplicate fallback without replacing the selected copy.
- The built page passed browser checks at 1280px and 390px using synthetic intercepted API responses: 60 rendered rows per page, folder selection retaining older basket items, visible selected names, no horizontal overflow and controls at least 44px tall. These are UI checks, separate from the database exercise, not a production end-to-end upload claim.

No production upload, job, model request, deployment or posting action was started. Deploy with the normal installer and run `python3 scripts/verify-phase29.py`. Follow the Create source-picker steps in [testing-plan.md](../testing-plan.md).
