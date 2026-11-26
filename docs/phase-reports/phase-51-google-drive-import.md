# Phase 51 — Explicit Google Drive library import

## Result

Library → Add media now separates local-device uploads from Google Drive selection while sharing the existing import name, destination folder, display-name prefix and video-role controls. The Google Picker grants access only to files the owner explicitly selects. A durable server queue downloads those files without keeping the phone or browser open, then hands them to the unchanged original finalisation, hashing, duplicate-storage, analysis and Library Inbox pipeline.

A separate CPU-only `cloud-importer` service owns network transfers so a large Drive download cannot block the editing/GPU worker. Partial downloads use byte ranges, update visible progress and retry transient failures up to five times. The imported Drive version is unique per connection and remote revision, preventing accidental duplicate downloads while allowing a changed remote file to be imported as a new original.

## Security and scope

The feature is owner-only and disabled until explicitly configured. OAuth uses a single-use, ten-minute state and the non-sensitive `drive.file` scope. Refresh tokens are encrypted with a dedicated appliance key; short-lived Picker access tokens are returned only to the authenticated owner with no-store requests. Provider errors are converted to bounded user-safe messages. No Drive listing, deletion, modification or automatic folder monitoring is implemented.

## Validation

- Python sources compile.
- Web TypeScript passes.
- Compose configuration parses with the new service.
- The production web build succeeds.
- All 136 media-selection and upload interaction checks pass, including the explicit no-import-before-connection Drive path.
- Transport unit coverage includes the exact OAuth callback/scope, encrypted refresh tokens, ranged resume and remote-ID path rejection. Container execution of the new Python unit file still requires local Docker permission or deployment CI.

## Deployment and acceptance

Run `scripts/configure-google-drive.py`, register the printed origin and callback in Google Cloud, and deploy migration 051 plus `cloud-importer`. Then test one small video before a large batch: connect, select, close the page during download, reopen the Inbox, confirm analysis completes, and use the imported original in an edit. Test a repeat selection to confirm no second download is created.
