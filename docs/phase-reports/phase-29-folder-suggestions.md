# Phase 29 follow-up — reviewed folder suggestions

The existing Auto-sort review now suggests folders alongside names, video roles and photo/audio categories. This closes the folder-suggestion part of the intake phase while keeping filing explicit. Source checkpoint only: root-managed deployment and owner acceptance remain pending.

## Resulting flow

Select up to 24 ready originals in Library or Inbox. **Suggest folders too** adds a bounded snapshot of up to 100 existing folder names to the same auto-sort request. The model can select an existing folder, propose one reusable topic folder, or leave a file unfiled. Folder names and supplied source evidence are data, not instructions. Unsupported/uncertain files receive no automatic folder proposal.

Review each name, label and destination. Choose an existing folder, edit a new name or choose **No folder change**. **Also apply folder choices** is off by default: names-only Apply preserves memberships. When explicitly checked, the same transaction saves reviewed metadata and adds selected files to their chosen folders. No background model call or automatic filing is added.

Existing memberships are preserved. Case-insensitive uniqueness reuses folders rather than duplicating them. Existing-folder identity/name checks reject renamed/deleted choices, metadata/version/hash checks reject stale source changes, and active-original checks reject trashed files. Collection locks precede asset locks; folder applications serialize against one another. Failures roll back the transaction, including newly created folders. Repeated successful application is a no-op. Saved suggestions retain the applied human edits and a folder-application receipt.

## Compatibility and cost

Migration 047 adds the opt-in and bounded folder snapshot to saved organisation sessions. Historical sessions remain names-only; cached analysis and originals are unchanged. Requests still use one bounded editor-provider call for up to 24 sources with existing preview/transcript limits and measured usage. Folder names add input when requested; there is no separate folder model request. Applying or reopening a review uses zero model calls. Successful reel-planning, timing, colour, audio and rendering settings are unchanged.

## Validation

- 724 backend tests passed, including local CPU renders; focused organisation checks cover closed schema, unsupported evidence, manual-name preservation, folder validation, explicit application, stale/deleted targets, additive retry, saved receipts and one model request. Final focused checks were rerun after receipt changes.
- 89 UI interaction checks cover explicit review/application, new-name validation, saved sessions, preserved failed review and identical retry payloads. Source suite covers TypeScript, production build, public audit and patch integrity.
- All 47 migrations and actual folder, inventory, request and metadata SQL executed in isolated PGlite. Checks cover historical names-only sessions, case-insensitive reuse, additive membership retries, notes/favourite preservation and transaction rollback.
- Phone/desktop browser checks use synthetic intercepted API responses, with no production writes or paid model requests. Manual footage acceptance remains open.

Deploy with the normal service installer, then run `python3 scripts/verify-library-organization.py`. Follow the folder-suggestion section in [testing-plan.md](../testing-plan.md). Nested folders, tracking/cutout work and real acceptance gates remain open in the larger roadmap.
