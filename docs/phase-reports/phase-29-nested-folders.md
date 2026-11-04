# Phase 29 follow-up — nested library folders

Source checkpoint: 2026-11-04. Migration 048 and root-managed deployment are required. Owner acceptance with a real library remains open.

## What changes

Folders can contain subfolders, up to four levels in total. Existing folders remain at the top level after migration. The library home shows top-level cards; opening a folder shows its immediate subfolders and only the media filed directly there. Breadcrumbs link back through the hierarchy. The sidebar groups descendants under their parents, and upload, Inbox, asset filing and concept-scope selectors show full paths.

**New folder** offers an explicit parent, defaulting to the open folder when another level is allowed. **Create a subfolder** uses the same submitted form. **Folder options → Move folder** moves the selected grouping and its descendants; it does not refile media or change files. Changes happen only after pressing the form's submit button. Failed changes preserve the form for review/retry.

Names remain case-insensitively unique across the library, preserving the existing reviewed auto-sort and folder identity contract. Use descriptive names such as `Cream B-roll` and `Soap B-roll`, rather than identical `B-roll` names under different parents. Existing auto-sort suggestions can select any saved folder by its unchanged ID; newly proposed folders are still created at the top level and can be moved afterwards. No new model call, background auto-filing or media reanalysis is added.

Folder counts, media search and **Find reel ideas from media here** refer to direct membership, not a recursive aggregate. A parent containing only subfolders can therefore show zero direct media. Open the intended child folder for its media or choose All active library media in Concepts. This avoids silently broadening the existing source scope when nesting is introduced. An item can still belong to several folders.

## Integrity and compute

- Migration 048 adds an optional indexed parent reference, a self-parent check and restrictive deletion. Existing IDs, names, memberships, original filenames/storage paths and historical job references remain intact.
- Create, move and removal operations serialize hierarchy changes with a transaction-scoped advisory lock. Validation rejects missing parents, cycles and moves that would put any descendant beyond level four. Checks inspect small folder metadata, not media bytes or source analysis.
- Move requests include the previously observed parent. A stale move returns a conflict instead of overwriting a newer move from another tab. Refetch the library before resolving a genuine conflict.
- A folder with children cannot be removed. Move or remove its subfolders first. Removing a leaf only removes that grouping and its memberships; originals remain in All media and existing edits.
- Rename uses its existing separate contract and cannot silently move a folder. Existing case-insensitive naming rules and auto-sort folder locks remain unchanged.
- The client indexes each immutable folder response once for bounded path lookups; no per-folder API requests, recursive media scan or hosted-model request is introduced. Main media browsing retains its existing server pagination. The folder metadata list itself remains unpaginated.

## Verification

The backend suite ran 760 tests: 759 passed and one unrelated rclone check was skipped. Fifteen folder checks cover source/reference preservation, parent creation, moving descendants, invalid/stale destinations, child deletion protection, depth bounds and explicit request schemas. The final related-library run passed all 56 checks, including malformed parent references.

All 99 UI interaction checks passed, including new tests for tree ordering, complete paths, depth-aware destinations, direct source scope, parent-bound creation, submit-only moves, failed retry preservation and preventing parent removal. All eight source-suite gates passed, including TypeScript, the production build and patch integrity.

All 48 migrations and actual route SQL executed in disposable PGlite 0.5.15 with pgcrypto. Migration 048 was also applied with existing folder memberships in place. Checks cover parent and direct-media counts, child preservation on a move, self-parent/missing-parent/restrictive-delete constraints, unchanged name uniqueness, transaction rollback and unchanged original rows. This isolated SQL check is not a production multi-connection load test.

Phone and desktop browser checks use intercepted synthetic API responses, not the production catalogue. Production deployment, bulk-library usability and owner playback of historical edits remain acceptance steps. No upload, render, social post or hosted editing request was started by this checkpoint.

## Owner test after deployment

1. Run the normal service installer, then `python3 scripts/verify-phase29.py`. That verifier reads the schema and folder tree without making changes.
2. Create a parent such as Products. Move one existing folder into it using Folder options. Open it from its card, breadcrumb and sidebar.
3. Create a subfolder and upload or file a small mix of video/photo/audio there. Confirm the upload destination shows the full path. The Inbox should show the same destination after transfer.
4. Move the parent elsewhere. Its subfolders and their media should remain together. Reopen an older edit to confirm it still has its sources.
5. Try removing a parent with a child: confirmation should be disabled. Remove an empty leaf if desired; its originals should remain in All media.
6. Open Concepts from a populated child and confirm that the source scope is that exact folder. Folder organisation should not change the successful editor defaults or request extra analysis.

Nested navigation and moves close the remaining folder-structure implementation slice. Large-scale intake/load acceptance and pagination of other source pickers remain separate work; this is not a claim that every Phase 29 acceptance gate has passed.
