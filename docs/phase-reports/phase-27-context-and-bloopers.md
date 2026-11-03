# Phase 27 — source context and recorded blooper bundles

Source checkpoint: 2026-11-03 UTC. Implementation is ready for owner deployment and real-footage acceptance. Phases 26 and 27 still need human playback acceptance; this report does not assert that comedy or overall story quality has been solved.

## What changed

Fresh library blooper discovery now builds one selectable bundle containing an attempted line, a specific transcript clue and its own recorded response. It enumerates later incidents in a long catalogue chunk, rather than only the first clue. Complete matching word timings supply the exact text and source bounds. A self-comment such as “that is hard to say” can be the response; no laughter or successful sales recovery is required. A nearby question followed by recorded uncertainty is a possible clue, not proof that a correct claim is a mistake.

The scan conservatively declines laughter-only material, clean repeated takes, unattached corrections, instructional examples, incomplete word data, long gaps and responses from other recordings. It retains at most six bundles per source and the existing discovery text ceiling. Setup/response text travels atomically with the evidence, so the budget cannot retain a lone “oops” while dropping its attempt. Human Avoid marks also exclude intervals between words. Purely visual gags and untranscribed reactions remain manual review work.

The existing concept call uses a closed schema requiring explicit incident IDs for modern blooper options. The server copies exact recorded bundles, checks citation identity and overlapping alternatives, and declines incomplete options without a paid repair request. Selection rechecks the bundle before creating a new job. Renderer scope checks preserve the selected attempted line and response as well as the incident clue. Existing saved sessions retain their historical contract; existing job bindings remain idempotent. No frozen edit is rewritten by deployment.

The concept cards and coverage text identify these complete bundles, retain source preview links and ask for human judgement. This checkpoint adds explanatory text to the existing layout rather than another setup control.

## Context and compute

Ordinary concept discovery receives bounded links to preceding passages, explicit spoken product mentions/aliases, qualifiers/numbers and takes with matching openings. Links cite only shared evidence IDs; text mentions do not imply visual identity, and shared openings are not equivalent claims. Context hints fit spare space under the same 36,000-character inventory limit, with at most 3,000 characters of optional links.

Manual blooper jobs can receive range-only attempted-line/response hints in their existing editor request. They reuse cached words, deduplicate identical source hashes, respect Avoid ranges and fit at most 1,800 characters of spare context. They do not force a selected story or replace the full transcript. Source selection and request budgets remain bounded.

No extra ASR, alignment, vision model, critique call or training loop was added. Stored transcript derivatives are hydrated only for relevant blooper sources, including clues in long chunks. Concept generation still uses its normal explicit model call; creating an edit still uses its normal editing request. This is not a claim that every edit's token total decreases.

## Verification and remaining acceptance

Regression coverage includes multiple late incidents, complete bundle citation, same-source response, word-timing corruption, normalized Unicode offsets, tutorial/clean-take rejection, Avoid gaps, range hints/context budgets, product aliases and qualifiers, render scope protection, failed new selection without writes, and existing-job replay. Historical v1 concept fixtures remain covered separately from fresh v2 discovery. The source suite also checks the unchanged render and subtitle paths.

Verification passed: 654 backend tests, including local CPU FFmpeg renders; 72 UI interaction tests; and all eight source-suite gates covering web/agent TypeScript, production build, Python compilation, Compose, public-release audit and patch checks. A disposable PostgreSQL-compatible database applied all 43 migrations and exercised the actual concept-request, result and selection SQL: bundle JSON/precise numeric citations round-tripped, blooper purpose was retained and the concept-to-job binding stayed unique. An isolated built-app browser check at 1280px desktop and 390px phone found no horizontal overflow or JavaScript/network errors; opening history and selecting an option created no work, and only the explicit Create preview click sent the selected concept ID. All fixtures were synthetic. No production deployment, real model request, social post or user-job mutation was performed.

Use the [acceptance checklist](../testing-plan.md#source-context-and-blooper-acceptance--2026-11-03) after rebuilding:

```bash
sudo ./scripts/install-service.sh
python3 scripts/verify-phase26.py
python3 scripts/verify-phase27.py
```

No migration follows 043. The helpers are read-only. Generate fresh blooper ideas for the new contract; simply retrying an older saved option retains its earlier evidence. Human listeners must judge whether the setup is understandable, the reaction is genuine in context and the resulting reel is worth watching. Static source previews and transcript clues cannot establish facial motion, delivery or humour.
