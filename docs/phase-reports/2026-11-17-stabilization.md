# Stabilization checkpoint — 2026-11-17

## Purpose

Consolidate the streamlined Create, review, composition and media-library work into a deployable checkpoint before inviting a second real editor. The checkpoint was deployed after its source and pre-deployment appliance evidence passed.

## Evidence available

- The owner reports successful real edits from both phone and laptop through the private deployment.
- `./scripts/verify-source-suite.sh` passed all eight gates.
- The browserless workflow suite passed 132 of 132 tests.
- The production web build generated all 29 routes.
- Compose configuration, Python parsing, public-release audit, web and agent TypeScript, and patch integrity passed.

## Pre-deployment appliance snapshot

The authenticated read-only health snapshot generated at `2026-11-17T04:37:08Z` reported:

- deployed build `8940fc24db6ca6454d9b7e04f75f3ae231cdc618`;
- all seven expected services running;
- no pending analysis, visual, catalogue, edit or final jobs;
- no job failures in the preceding 24 hours;
- 23% disk use with about 702 GB available;
- a checked encrypted local backup completed at `2026-11-17T03:27:46Z`;
- a checked encrypted off-site copy last verified at `2026-11-16T05:13:35Z`.

This is the rollback baseline used for the rollout.

## Post-deployment verification

The controlled restart completed successfully at 3:18 pm AEST on 17 November 2026. Independent authenticated checks then confirmed:

- deployed build `307fbbcdd455350acd1cc55743fc99ffd584e303`;
- all seven expected services healthy and all application timers active;
- no pending analysis, visual, catalogue, edit or final jobs;
- no job failures in the preceding 24 hours;
- migration 050 active, demonstrated by the persisted job composition contract;
- the appliance health summary remained healthy after the restart.

## Deployment acceptance still required

1. Retain the complete `sudo ./scripts/verify-live-suite.sh` terminal result with the deployment evidence.
2. Run the opt-in render/AI lane in a maintenance window.
3. Review real outputs for ordinary speech, exact script, multi-source B-roll, green screen, transitions, captions and effects.
4. Test a second real Tailscale identity as Editor and confirm owner-only routes are refused.
5. Record Dubai upload, queue, render, playback and download observations against exact job IDs.

## Pilot boundary

GM Studio is a shared private appliance. An Editor can create and revise videos and can see the shared library and job workspace. This is suitable for a trusted pilot, not independent customer tenancy. Tailscale device sharing plus the app-level Editor role is the preferred least-privilege pilot route.
