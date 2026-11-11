# Phase 32M — Effect Decision Receipt

Implemented in source on 2026-11-11. Deployment and owner acceptance remain pending.

## Purpose

The editing agent can already place native effects, but the finished preview previously showed only what survived into the cut. That made an effect-free edit ambiguous: the agent might have chosen restraint, effects might have been disabled, a local budget might have removed a proposal, or the render might simply be replaying an older saved plan.

This phase records those distinctions in the existing **How this edit was made** receipt.

## Implemented result

Editing receipt version 2 records one decision row for each of the eleven registry effects:

- **Selected** — the effect exists in the saved executable plan. The receipt identifies whether it came from fresh AI planning, a saved-plan replay or local controls and lists each exact reel interval and strength.
- **Rejected** — the AI plan proposed the effect but a named GM Server rule removed it. The first recorded rejection is the shared effect-budget check, which remains local and adds no model request.
- **Skipped** — the final saved plan contains no instance. The receipt does not claim that the model consciously considered an effect when no such evidence exists.

Two structural skip reasons are proven locally:

- Paper Tear reports when the saved plan has no ordinary cut with enough incoming duration.
- Dolly Zoom reports when no complete 1–8 second video clip remains without a conflicting camera treatment or picture layer.

Other unselected effects retain the honest **owner review** eligibility state because their suitability depends on picture meaning, movement, wording or taste. When effects are disabled, every unselected effect says so directly. Saved-plan replay and local-control previews explicitly state that no fresh AI effect decision occurred.

The receipt is deterministic and adds zero model tokens. It is saved in the preview manifest and copied into approved final exports, so the reviewed decision record cannot be silently rewritten during export.

## GM Studio presentation

The existing receipt now contains a collapsed **Effect decisions** section with selected, rejected and skipped totals. Opening it shows:

- registry labels rather than internal preset names;
- eligibility or exclusion state in text as well as colour;
- the recorded reason;
- exact timing evidence for selected effects; and
- an explicit warning that the receipt records returned plan data and local rules, not hidden model reasoning or a quality score.

Legacy version 1 receipts remain readable and do not display invented effect history.

## Verification

- Receipt tests require version 2, registry version 11 and eleven decision rows.
- A selected Clone Row retains its exact 0.50–1.50 second interval and strength.
- A one-clip plan records Paper Tear as structurally ineligible.
- Shared-budget coverage records the exact native preset removed by the local limiter.
- Browser coverage renders all three decision groups, timing evidence, local rejection reason and the no-hidden-reasoning notice.
- Browser coverage confirms legacy receipts still render.
- Python source compilation and web TypeScript pass before the full source suite.

The host does not contain the worker Python dependencies, so worker unit execution remains a post-deployment container check.

## Owner acceptance

1. Deploy this build and create a new automatic edit with effects set to Social or Meme-heavy.
2. Open the completed preview and expand **How this edit was made**.
3. Open **Effect decisions**.
4. Confirm the totals match the listed Selected, Rejected and Skipped groups.
5. For each selected effect, jump to the recorded time in the preview and confirm the named treatment is present.
6. Confirm an effect-free edit explains that effects were optional or disabled rather than claiming a failure.
7. Restore or export an older preview and confirm its original receipt remains unchanged.

## Next slice

Build conservative automatic-effects mode around explicit eligibility candidates. The agent should choose only from locally eligible candidates, retain its short source-backed rationale as plan data and default to no effect when evidence is weak. Owner approval/removal feedback can then be recorded for later preference learning without silently changing current edits.
