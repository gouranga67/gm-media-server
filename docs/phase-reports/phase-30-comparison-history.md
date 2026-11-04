# Phase 30 — Complete trial readiness and comparison history

Source checkpoint: 2026-11-04. Migration 049 deployment and real owner acceptance pending.

## Behaviour

Learning previously based part of its dashboard readiness report on the latest 100 displayed trial previews. The promotion endpoint already checked every trial for the chosen lesson. A queued or unreviewed older trial could therefore block activation after the page appeared ready. Both paths now use the same report builder and every saved trial state for that lesson. Existing independent-footage, score, usage, checklist and executable-change requirements remain in force; no lesson changes status during installation.

Each displayed lesson has **Browse all comparisons for this lesson**. Opening it loads 20 trials with exact baseline/trial playback, saved scores and recorded token/latency totals. Older, newer and most-recent controls use a creation-time plus run-ID cursor, including a stable tie-breaker when timestamps match. The owner-only read endpoint permits at most 50 rows per request. It returns a conflict for a removed or foreign cursor; failed navigation keeps the previous page and review drafts available. Missing baseline/preview files remain visible but cannot be scored.

Unsaved ratings, checklist choices, notes and playback attestations survive changing pages or toggling back to recent comparisons while the Learning page stays open. Each review still requires an explicit save. Leaving or reloading the page discards unsaved drafts; this is not persistent draft storage. Refreshing history reads saved results without starting an experiment.

## Compute and data

The overview fetches lightweight trial-state metadata for its displayed lessons in one batch. File availability and model-usage hydration stay limited to the displayed previews; a history request checks only its bounded page. Videos retain `preload="none"`. Migration 049 adds a partial lesson/time/run index including trial status and case ID; it does not rewrite scores, runs, media or settings. Browsing, checking readiness and installing the index add no hosted model calls.

The overview still limits lessons, cases and activation events to their latest 100 records. Per-lesson trial pagination does not remove those separate list limits. Readiness includes all trials for each displayed lesson; it does not imply automatic evaluation, promotion, model training or demonstrated story improvement. Saved comparisons remain subjective evidence under the previously documented provenance and experimental limits.

## Verification

- Backend: 768 tests run, 767 passed and one unrelated disposable rclone retention integration skipped because rclone was unavailable. This includes eight new full-history, pagination, missing-file, owner-access and zero-write regressions, plus the existing local render checks.
- UI: all 103 interaction tests passed, including lazy history loading, retained review drafts, failed-page retry and refreshing the current page after saved state changes.
- All eight source-suite gates passed, including TypeScript, production web build and the public-release audit.
- An isolated PostgreSQL-compatible database applied all 49 migrations and executed the actual history, score, usage and state queries. It paginated 105 trials with identical timestamps across six pages without repeats, omissions or cross-lesson rows; preserved a missing-baseline row; and confirmed the index upgrade preserved existing runs.
- The built page passed browser checks at 1280px and 390px with synthetic intercepted API responses: no horizontal overflow, controls at least 44px tall, retained notes after older/newer navigation and no mutation requests. These UI checks are separate from the isolated database test, not a production end-to-end playback claim.

No live trial, score, promotion, deployment, publication or production data mutation was performed. Use the normal installer and `python3 scripts/verify-phase30.py`, then follow the Learning acceptance steps in [testing-plan.md](../testing-plan.md). Actual independent-footage comparisons remain the Phase 30 exit evidence.
