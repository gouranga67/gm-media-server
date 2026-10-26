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

## Checkpoint 2: local finishing and evaluated lessons

The main editing-tool implementation is now present. This is a source checkpoint, not a claim that every proposed research capability or the real-user pilot has passed.

### Editing and finishing

The review screen exposes precise source trims/slips, source-time splits, word boundary shortcuts, bounded pause tightening, and picture transitions. Changes create versions, validate before queueing, and reject stale clip handles or preview versions. The API and typed agent tools also support replacement takes from the same job. Ready previous versions can be restored as a new preview. These controls remain accessible after final export under **Make another version**.

Optional local finishing adds up to six camera control points per move, phrase-level voice gain, timed caption placement/hiding, gentle voice denoising, selected-clip colour controls and a start position inside the selected licensed music track. New picture layers support contained review cards, fade/slide entrances, picture-in-picture, circle masks, alpha transparency, opacity and real green/blue-screen keying. Only attached sources are accepted. Silent video layers can be retimed or frozen without changing speech speed.

Independent recorded-audio joins support J/L cuts with source and reel bounds, neighbouring speech checks and captions mapped to the actual audible source. Overlapping joins are refused; clear them before a source trim or timeline rearrangement. Prefix delivery variants retain compatible joins. Optional picture dissolves blend the outgoing held frame with the incoming picture while preserving dialogue duration; ordinary cuts and dips remain available. Existing frozen plans remain compatible, and picture-layer provenance includes source hashes.

The normal first-pass planner still uses the established schema and model. Advanced finishing is exposed through local review controls and typed agent operations; adding these tools does not make every first-pass edit apply them automatically. There is no default second critique request. Natural-language story revisions continue through the existing bounded editor path. Do not assume that a free-text request can invoke every new precise tool: the explicit controls provide the dependable path.

### Evidence and compute

Image OCR is local and bounded, with confidence and normalized text coordinates. It is recognized text, not proof of identity, factual correctness or complete visual understanding. Source ranges marked **Avoid** are excluded from concept speech retrieval and rejected in new story planning; a later annotation does not invalidate a frozen edit. Product mentions share a vocabulary across editing and concept retrieval. Rich source evidence stays on the appliance; hosted payloads omit duplicated dialogue and retain small boundaries, notes and OCR excerpts. Large concept metadata inventories compact before speech selection, retaining source coverage within the existing text budget. Text-only privacy permits recognized text/metadata, while original/image files remain excluded; local-only editing continues without hosted requests.

Runtime samples distinguish planning and rendering inside the worker, as well as whole task classes. Cached transcription retains the existing recognition settings and model; neither warm weights nor the inference mutex constitutes a guarantee of GPU memory isolation. Live latency, CUDA contention and NVENC acceptance still require the actual appliance.

### Learning

Feedback can identify a topic and a time range. Explicitly proposing lessons scans saved notes locally against a small, fixed set of editorial patterns. It requires three distinct training jobs and preserves recipe/style scope; repeated revisions of one job cannot manufacture support. Raw feedback notes never become arbitrary system instructions.

Trying a proposed lesson is an explicit normal editor revision and uses model tokens. The lab preserves a baseline and trial preview for paired playback ratings. Training jobs and source hashes are excluded from hold-out trials. Promotion requires at least three distinct held-out jobs, no lower candidate rating, and at least one improvement. Promotion adds bounded guidance; rollback removes it from future context. Existing tag-derived preferences remain separate. No model weights or application code are rewritten.

One-pass local repair can tighten measured speech gaps or apply gentle denoising. One repair is allowed per source version, with no background repair loop or extra model request. Gap tightening can shorten a comic pause, so it remains an explicit user choice.

### Pilot boundary and remaining gates

**Studio → Pilot acceptance** states the shared private-studio boundary and provides the live/human checklist. It does not certify itself from checkmarks. The read-only verifier checks deployment contracts without creating a job or making a hosted request.

Not shipped/enabled in this checkpoint: automatic subject tracking; learned person/background segmentation; optical-flow retiming; isolated public customer workspaces. These remain gates in the roadmap, requiring a chosen licensed model or a separate isolation implementation, appliance resource measurements and real quality/security acceptance. Colour controls are adjustments after existing colour management, not an automatic shot-matching model. OCR coordinates do not yet provide an automatic proof-text highlight editor.

## Final source verification

- 311 backend tests passed, including actual FFmpeg software renders. A subsequent nine-test finishing pass also verified measurable voice gain, blended dissolve frames, audio-join duration and legacy compatibility.
- 23 interface interaction tests and all eight source-suite checks passed, including TypeScript, production web build and the release audit.
- All 31 migrations and the new SQL operations passed against an isolated PostgreSQL-compatible test database, including the one-repair uniqueness guard.
- Seven pages were checked at phone and desktop widths (14 rendered views) with synthetic API fixtures: no JavaScript errors, horizontal overflow or automated WCAG 2 A/AA violations. These checks do not replace real-user accessibility and playback testing.

## Deployment and acceptance

From the project directory on the appliance:

```bash
sudo ./scripts/install-service.sh
python3 scripts/verify-phase19-25.py
sudo ./scripts/verify-live-suite.sh
```

After the core suite passes, the existing explicit render/AI lane can be run if desired:

```bash
sudo ./scripts/verify-live-suite.sh --confirm-render-and-ai
```

The source session could not access the production Docker socket or perform a sudo deployment. It used isolated PostgreSQL and actual local FFmpeg software renders, synthetic HTTP interface interactions and a production web build. Hardware encoding, live service deployment and the human pilot remain acceptance work.

Start with a known good reel: trim one word range; make a picture dissolve; move captions for a two-second window; add a review-card layer; listen to a phrase-level audio change. Compare against the previous version and export. For J/L cuts, choose an actual quiet neighbouring boundary. For learning, propose lessons, then use genuinely fresh footage for three paired comparisons before promotion. Review playback rather than relying only on a successful render or local story hints.
