# Phase 32C — Live Cursor

Implemented and source-verified on 2026-11-11. Container render verification, deployment and owner playback acceptance remain pending.

## Purpose

Live Cursor is the first new effect added through the reusable Effects Engine contract. It demonstrates that a new social animation can be registered once and become available to validation, the editing agent, GM Studio, both render paths, manifests, treatment review and tests without creating a separate application.

This is a bounded pointer animation, not object tracking or a claim that the owner clicked something that is absent from the footage.

## Implemented result

Native effect registry version 2 adds **Live Cursor** with:

- a 0.4–4.0 second duration and 1.5 second default;
- subtle, standard and strong pointer sizes;
- normalized start and end coordinates limited to safe frame ranges;
- an explicit on/off click pulse at the destination;
- unchanged recorded dialogue and caption priority above the animation;
- no segmentation, browser renderer, arbitrary FFmpeg expression, URL or generated replacement footage.

GM Studio reads these controls from the server registry. Choosing the effect fills safe defaults and performs no render. Explicit submission sends one typed `visual_beats` entry. The treatment review records the coordinates, click choice and absence of tracking; the finishing manifest records registry version 2 and the complete bounded effect document.

The editing agent can choose the same effect, but its instruction restricts use to a genuine visible on-screen target supported by the analysed footage. It must not imply a click or action that did not occur. The existing effects-level preference still controls whether decorative effects are allowed at all.

The renderer uses a native ASS vector pointer beneath dialogue captions. The pointer moves on the existing video clock and an optional short vector ring appears at the endpoint. Audio is not filtered or retimed. Both talking-head and montage rendering receive the same caption/treatment file.

## Verification added

- Registry tests cover version 2, parameter types, safe coordinate ranges and click defaults.
- Model tests reject missing, out-of-range and misplaced cursor parameters.
- ASS tests verify the bounded move, vector pointer, click pulse and layer below captions.
- Real FFmpeg coverage exercises Live Cursor, Clone Row and Impact Frame through both render engines while checking continuous audio and visible subtitles.
- Browser interaction coverage verifies that registry defaults populate the controls, selection performs no request and explicit submit sends only the bounded fields.
- The synthetic preview includes a Live Cursor sample and reports all three native effects.
- `scripts/verify-phase32.py` checks the deployed registry read-only without starting a render or model request.

The complete eight-gate source suite passes: Compose configuration, Python compilation, public-release audit, web TypeScript, all 112 browser interaction tests, agent-tool TypeScript, production web build and patch-integrity checks. The host has neither the Python application dependencies nor access to the root-managed Docker daemon, so the new Python model and real FFmpeg assertions must run in the worker container during deployment acceptance.

## Acceptance required

1. Run the native-effect test module in the worker image.
2. Run the synthetic preview and inspect the cursor movement, endpoint pulse, existing Clone Row and Impact Frame stills.
3. Deploy and run `python3 scripts/verify-phase32.py`.
4. Apply Live Cursor in GM Studio with and without its click pulse.
5. Check vertical and landscape footage on phone and desktop, including caption overlap and target accuracy.
6. Let an AI edit use it on footage with an obvious on-screen target, then confirm the choice is useful and truthful.

## Next slice

Phase 32D should add **Letter Dive** as the next low-risk overlay animation, retaining the same registry, explicit-submit, dialogue-preservation and real-playback gates. Comment Drop and Voice Note can follow one at a time. Camera-like effects and transitions such as Rack Focus, Dolly Zoom and Paper Tear remain a later shot-aware pack.
