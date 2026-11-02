# Combined acceptance checkpoint — 2026-11-02

The application build `84b96419` is deployed. Its live learning contract reports version 2, including the migration-040 evidence requirements. The technical checks below passed. Creative playback, the container-based core suite and prospective learning trials remain separate acceptance tasks.

## Evidence collected

| Check | Result | Scope and limits |
| --- | --- | --- |
| Backend and local render regressions | 536 tests passed, no skips | Includes real local FFmpeg fixtures. This run used temporary host test dependencies; the pinned worker-container run remains pending. |
| Source suite | 8 gates passed | Includes 54 browser interaction tests, both TypeScript surfaces, production web build, Compose, Python syntax, release audit and patch checks. |
| Read-only live verifiers | 8 passed | Sprint readiness, brief-first interpretation, library concepts, organisation, publishing readiness, learning readiness, creative inventory and complete job history. No model or publishing request was made. |
| Deployed browser inspection | 27 page views across desktop and phone widths | No observed horizontal overflow, visible error alerts, HTTP failures or uncaught JavaScript exceptions. Non-read requests were blocked. This is not a full accessibility or physical-device audit. |
| Revision typing | Passed | Entering a note in an isolated browser produced no mutating request. Submission and editorial response still require deliberate playback testing. |
| Live GPU fixture | Passed on `h264_nvenc`, zero model tokens | An isolated local-only verification job referenced existing media and rendered camera animation, a picture dissolve and timed caption placement. Its treatment report contained all three event kinds; an invented source was rejected and a valid MP4 was served. The fixture job was archived after completion. Existing edits were not revised. |
| Host and backup status | Healthy at inspection | Service active, ample memory/disk headroom, local and off-site backup services last reported success. No new restore or reboot drill was run. |

The live inventory exposed 24 music tracks and 68 creative effects. Meta publishing is not configured and has no connected accounts; readiness passing does not establish actual posting. Library readiness reported four sources still processing and no analysis failures at inspection; this snapshot does not establish whether an individual source is stalled.

Browser screenshots and detailed logs were kept in temporary local files, outside repository history. No private media, prompts or credentials are included in this report. No hosted lesson trial, learning promotion, publication or storage cleanup was performed.

## Verification changes made during this pass

- Phase 14 readiness now only reads learning state. The old helper temporarily overwrote a real rating and restored an incomplete copy, losing topic/timing details. Feedback creation and updates remain covered by local tests and deliberate user acceptance.
- Phase 5 rendering now creates its own local-only verification job instead of submitting a test plan to an existing working job. Only its terminal fixture is archived; interrupted active renders remain visible. Download acceptance is labelled as an MP4 response rather than physical-phone playback.
- The core suite mounts the host scripts read-only alongside tests so the new verifier-isolation regressions also run in the worker image.

These are host verifier/test changes; another application rebuild is not needed solely to run them.

## Remaining acceptance

1. In the server terminal, run the container-based core suite:

   ```bash
   cd /home/gm/projects/gm-media-server
   sudo ./scripts/verify-live-suite.sh
   ```

   Docker access requires an interactive sudo login. This lane includes reversible verification fixtures and settings round trips; it is not wholly read-only. Do not run it alongside valuable editing work. The additional render/AI lane remains opt-in.

2. Work through the first eight [hands-on checks](../user-acceptance-checklist.md), one fresh test job at a time. Prioritise a familiar good reel, an actual targeted revision, a multi-source concept, a genuine blooper and downloaded phone playback. Judge complete words, coherence, colour, intelligibility, picture support and effect relevance by watching and listening. A treatment manifest describes the plan; it does not establish visibility, humour or engagement.
3. Evaluate a proposed lesson only after playback on genuinely fresh, checksum-independent footage. Three independent qualifying groups, no regressions and an executable improvement are required. Comments alone do not establish that the system learned a better editing rule.
4. Complete recovery, shared-user and Meta posting acceptance in their separate documented lanes. A successful backup status does not replace a restore; a publishing readiness response does not replace account setup and an explicitly authorised real post.

One follow-up coverage gap remains outside this checkpoint: the legacy typed `submit_edit_plan` talking-head adapter offers cut/black-dip transitions while the web planner and renderer also support picture dissolves. The GPU fixture used the direct plan endpoint; it does not certify parity of that adapter's available tools.

The next gate is user/pilot acceptance, not automatic promotion of all phases based on technical test counts.
