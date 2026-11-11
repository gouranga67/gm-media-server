# Phase 32L — Effects Gallery and eligibility guide

Implemented in source on 2026-11-11. Deployment and owner phone acceptance remain pending.

## Purpose

Eleven native effects no longer fit comfortably in an unexplained dropdown. The renderer and effect parameters were already bounded, but choosing the right treatment still required remembering what each name meant, what footage it suited and which restrictions would reject it.

This phase makes that decision visible without starting a render or pretending that GM Studio can judge subjective shot quality automatically.

## Implemented result

Native effect registry version 11 adds durable **best for** and **avoid when** guidance to every effect. GM Studio presents the registry as five compact groups:

- **Accent** — Impact Frame, Clone Row and Live Cursor;
- **Social** — Voice Note and Post Wall;
- **Text** — Letter Dive, Comment Drop and Sketch Words;
- **Camera** — Rack Focus and Dolly Zoom; and
- **Transition** — Paper Tear.

Each card has one of three truthful states:

- **Ready** when the editor has enough structural evidence to configure the effect;
- **Check shot / wording / speech / target** when human judgement or source-backed input is still required; or
- **Unavailable** when a concrete cut constraint fails.

Paper Tear reports whether the saved cut contains an eligible ordinary boundary. Dolly Zoom reports whether an eligible complete stable video clip remains after camera, tracked-framing and layer conflicts are excluded. Rack Focus is deliberately not marked automatically ready: the owner must confirm a stable shot and two clear visual targets. Text and social treatments ask the owner to verify source support instead of claiming semantic certainty.

Selecting a gallery card only changes local form state. It does not call the editing agent, queue work or create a preview. The existing selector remains as a compact keyboard/native-control alternative. Explicit **Create preview with this tool** submission remains the only mutation.

The selected-effect panel now shows:

- the effect summary and duration bounds;
- registry-backed best-use and avoid guidance;
- a three-item playback checklist tailored to transition, camera, pointer, text/social or accent/layout effects; and
- the unchanged speech and caption-layer contract.

The gallery follows GM Studio's existing paper-and-harbor design system, preserves visible focus states and minimum touch targets, and communicates status in text as well as colour.

## Verification added

- Registry unit coverage requires version 11 and non-empty best-use and avoid guidance for all eleven effects.
- The deployed-registry verifier rejects version 10 or any effect missing its guidance contract.
- Browser coverage confirms all eleven cards and five groups are present.
- Browser coverage confirms an ineligible Paper Tear explains the missing ordinary cut before submission.
- Card selection is verified to make no revision request.
- The unavailable effect can still be selected to inspect its explanation, while preview submission remains disabled.
- The existing per-effect browser tests continue to verify exact payloads and explicit submission.
- The complete source suite covers TypeScript, 121 browser workflows, the production web build, Compose validation, public-release auditing and patch integrity.

The host Python environment does not contain the worker dependencies, so the real worker unit test remains a deployment command. Source compilation and browser/build verification run on the host.

## Owner acceptance

1. Deploy the source and open a completed job on the phone.
2. Expand **Finishing tools · local preview**, then choose **Visual effect / animation**.
3. Confirm the gallery shows Accent, Social, Text, Camera and Transition groups.
4. On a one-clip edit, select Paper Tear and confirm it explains why it is unavailable and keeps the preview button disabled.
5. On a two-clip ordinary cut, confirm Paper Tear becomes Ready and names the boundary.
6. Select Rack Focus and confirm it asks you to check the shot rather than claiming automatic depth or tracking.
7. Select a text effect and confirm the best-use, avoid and playback-check guidance is useful.
8. Browse several cards and confirm no preview appears until **Create preview with this tool** is pressed.
9. Create one effect preview and confirm speech timing and dialogue captions remain intact.

## Next slice

Run the real-footage effects acceptance pass for Rack Focus, Paper Tear and Dolly Zoom, then add an agent decision receipt that explains why an automatic edit selected, rejected or skipped each eligible effect.
