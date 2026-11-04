# Phase 30 — Saved playback evaluation

Source checkpoint: 2026-11-03. Deployment and real held-out quality acceptance pending.

## What changed

Studio → Learning now has **Reusable playback test cases**. Save a playable ordinary edit, name its recording session, and describe what a successful edit must preserve. Registration stores the exact baseline run and plan hash, every attached source checksum, stored analysis fingerprint, source labels/ranges and job settings/brief. It never copies originals or starts a model. Ordinary job status changes and the completed-version counter do not invalidate a case; changes to editing inputs do. A case is rechecked before queueing, before planning and before scoring. Changed inputs require a fresh ordinary baseline/case.

Cases can be reused across different proposed lessons. A lesson trial keeps the selected baseline even when another trial has become the job's latest version. Retries reuse the same lesson/baseline/case request. Test expectations guide the human comparison; they are not extra instructions secretly sent to the editor. The existing proposed lesson directive is the trial instruction.

Active cases protect their baseline previews from routine retention. Proposed lessons continue protecting both sides of their comparisons. Archiving a case releases its baseline's additional protection, subject to other existing retention guards; it does not immediately delete a preview or original. Restoring a case does not recreate an already-expired preview. Cases/criteria are immutable through this API; archive rather than changing the task after seeing its result.

## Evidence and activation

Migration 045 introduces saved cases and application-append-only activation events. New lessons use evaluation protocol 2. Existing lessons remain on protocol 1, including promoted ones: installation does not silently deactivate or promote rules. An inactive legacy lesson can be explicitly upgraded. Old scores remain visible but cannot add positive evidence or regressions to the new protocol's cohort; fresh case-bound trials are required. An active lesson must first be rolled back to upgrade it.

Each case-bound comparison requires both exact previews, overall baseline/trial ratings, an explicit watched-both attestation and six verdicts: brief/test criteria, story/ending, complete words/sync, captions, visuals, and audio. Verdicts are better, same, worse or not applicable. This is an owner attestation, not automatic proof that every frame was watched. A higher overall rating cannot hide a recorded checklist regression. A changed executable edit, positive overall preference and at least one specific checklist improvement are required to count as an improvement.

Promotion requires at least three independent footage groups, none using the lesson's training footage. Shared source checksums and repeated job IDs merge comparisons; the same normalized owner-supplied recording-session label also merges them. Files from one shoot should use one group name. This does not automatically detect all related recordings, people or themes. Every case-bound queued trial must finish and every ready pair must be scored before promotion. Failed attempts are reported and cannot add qualifying evidence; they are not automatically disqualifying because infrastructure/provider failures can be unrelated to the directive. The owner must inspect failures as well as successes.

Protocol 2 additionally blocks qualification when measured usage is missing, a supplied candidate-token ceiling is exceeded, or the candidate introduces new local technical-warning codes. Known recorded local execution can have zero model calls; an unknown/missing provider record is not treated as free. Tokens are usage, not a currency price. Recorded model latency excludes queueing, upload, analysis and rendering. The optional ceiling checks the result after the trial; it is not a provider spending cap. Local technical checks are fallible and do not judge story or comedy quality.

Explicit promote, rollback and protocol-upgrade actions record a monotonically increasing deployment version, rule hash, actor and supporting evaluation snapshot. Repeating the same status action adds no duplicate transition. The server rechecks all trial readiness before promotion, even when the page shows only recent rows. Rollback stops future use of that lesson; it does not rewrite completed edits. This is versioned activation of the existing bounded rule templates, not arbitrary self-written code, changing model weights, or an automatic critic loop. Existing tag-derived preferences and bounded local timing/audio repairs remain separate.

## Limits of the comparison

Saved cases freeze the task/source/baseline inputs described above, not the whole global music/effects catalogue, deployed build, global preferences or stochastic model state. Models and measured usage are recorded with the score. Keep those broader conditions stable when comparing trials, and treat preference as evidence rather than proof that one directive alone caused the improvement. Do not archive or discard inconvenient trials to manufacture a preferred result.

The overview lists the latest 100 cases, trial previews and activation events, plus the latest 100 lessons. The [comparison-history follow-up](phase-30-comparison-history.md) adds owner-only per-lesson trial pages and makes the dashboard readiness report use every trial for each displayed lesson, matching the promotion endpoint. Pagination of the lesson/case/event lists remains future work. Saving a case requires complete analysis/checksums for at most 100 attached sources. No extra media recognition model, hosted critique, paid trial, score, promotion or social post runs automatically.

## Validation and acceptance

Technical validation covers saved-task provenance, retries/conflicts, stale input rejection, exact baseline binding, complete checklist requirements, recording-group overlap, unchanged edits, speech regressions, missing usage, token ceilings, new warnings, queued/unreviewed comparisons, protocol upgrades and transition history. Actual migration/query execution uses an isolated PostgreSQL-compatible database, never production media. Phone/desktop checks use synthetic intercepted API data.

The checkpoint passed 700 backend tests, including local CPU FFmpeg renders; 83 UI interaction tests; TypeScript and production web build; all eight source-suite gates; and isolated execution of all 45 migrations and the actual case/trial/evaluation/retention SQL. See [testing-plan.md](../testing-plan.md) for the required real-footage comparisons. Passing deployment readiness is not demonstrated creative improvement. No real paid experiment or rule promotion was performed while building this checkpoint.
