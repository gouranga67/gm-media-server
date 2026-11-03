# Folder-first library — 2026-11-03

Implemented in source; application deployment and real-library acceptance remain pending.

## Behaviour

Library opens on folder cards with representative thumbnail covers and active, ready item counts. Existing collections appear as folders without copying or moving original files. Folders are flat in this increment; an item can belong to several. The sidebar offers All media, Not in folders, Favourites and Trash. Counts include ready active records; the existing repeated-upload grouping can reduce the number of rows displayed inside a folder.

Inside a folder, existing speech/scene/name search and footage/category filters remain constrained to its members. Grid and compact list modes share selection and actions. Folder, display mode, filters and search are remembered in per-tab session storage; scroll position is restored on return. Selections are deliberately not replayed after leaving. A missing remembered folder falls back to the overview. Blocked or malformed browser storage does not prevent browsing.

New folder and rename require form submission. Removing a folder requires confirmation and removes only its grouping. Bulk Add to folder and Remove from this folder use bounded, unique selections of up to 500 source IDs in one database transaction. Missing sources reject the whole operation before a membership write. Adding the same item again is idempotent, and membership changes preserve other folders, original media, analysis, names and existing job references. Hidden search results are excluded from bulk actions. Failed requests retain the selection and show the server error.

The source inspector keeps its existing preview, transcript/scene evidence, range annotations, editable metadata and folder memberships. On phones it opens as an overlay rather than appearing below a long media list. Escape closes it, and focus returns to the opening control. Folder options are collapsed and primary actions are kept short on small screens.

Find reel ideas from this folder opens a fresh concept brief with that folder preselected, without generating anything or reopening an unrelated previous session. Normal concept submission remains explicit and uses the existing editing/analysis policy.

## Scope

There is no new migration, hosted request, automatic organisation, file duplication or physical file deletion. Collection API identities and memberships are reused. Existing client pages that call these collections still work. Uploading directly into a folder, nested folders, an analysis/organisation Inbox, reviewed AI folder suggestions, drag-and-drop filing and browsable per-recording moments are later increments. The browser still loads managed metadata through the existing paginated all-assets helper; only the displayed cards/thumbnails are limited. Full server-side browsing/filter pagination is not claimed here.

Superdesign's existing library draft was read, but automatic approval review blocked exporting private source context for a remote revision. The implementation and rendered layout were designed and reviewed locally instead; no new canvas draft is claimed.

## Verification

- 544 backend/local-render regressions passed without skips, including eight new folder tests for idempotence, atomic rejection and preservation of originals/other memberships.
- 61 browser interaction tests passed, including folder-only search, photos in bulk membership, error/selection retention, explicit folder submissions, remembered browsing scoped concept navigation and explicit recovery from an unavailable folder shortcut.
- An isolated PostgreSQL engine applied all 40 migrations and exercised the actual folder query strings: counts/covers, repeat additions, rename, archived exclusion, membership removal and folder deletion with originals retained.
- A standalone production build was inspected in isolated Chromium against synthetic local fixture data at 1440px and 390px widths. Overview, grid, list, selection and inspector states had no observed root overflow, visible errors or JavaScript exceptions. This is layout inspection, not a real-device or live-data write test.
- Both TypeScript surfaces, Python compilation, Compose, production build, public-release audit and patch checks are covered by the source suite. An older acceptance report contained a machine-specific command path; it was made portable so the audit passes.

No production media, folder membership, job, model request or publishing state was changed for these checks.

## Deployment and acceptance

From the repository directory on the server:

```bash
sudo ./scripts/install-service.sh
python3 scripts/verify-library-organization.py
```

Then open Library and check:

1. Existing collections appear as folders. Create one test folder and inspect Grid/List at phone and desktop widths.
2. From All media, select a video and a photo, choose the folder and press Add to folder. Both originals remain in All media.
3. In the folder, filter/search, open a preview, close it, leave the page and return. The folder and display choices return; stale selections do not.
4. Remove one member, then rename and remove the test folder. Other folders and existing edits still work; the sources remain available.
5. Open Find reel ideas from this folder on a populated real folder. Confirm its scope before choosing whether to submit a paid generation request.

The container-based core suite and physical-phone/live-library write acceptance remain operator-run checks after deployment.
