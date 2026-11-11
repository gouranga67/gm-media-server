# Phase 32K — Dolly Zoom

Implemented in source on 2026-11-11. Container verification, deployment and real-footage quality acceptance remain pending.

## Purpose and limitation

A real dolly zoom combines physical camera travel with an opposing lens zoom, changing background perspective while the subject remains a similar size. GM Media Server cannot reconstruct that missing camera motion from an ordinary flat recording. This implementation is therefore an honest dolly-style illusion: it animates a bounded crop and scale around one fixed frame anchor over one complete stable clip. It performs no depth reconstruction, segmentation, subject locking or real parallax.

The limitation is visible in GM Studio, agent guidance, treatment review and this report. The effect should be rejected when edge cropping removes important information, the fixed anchor drifts away from the subject or the source already contains strong camera movement.

## Implemented result

Native effect registry version 10 adds **Dolly Zoom** with:

- one complete 1–8 second recorded video clip as its immutable scope;
- push-in and pull-out directions;
- subtle, standard and strong crop amounts of 8%, 14% and 20%;
- horizontal anchors from 0.30–0.70 and vertical anchors from 0.25–0.75;
- no stacking with another camera move, tracked reframe or overlapping picture layer; and
- unchanged dialogue, music, source duration and caption timing.

GM Studio lists only eligible video clips and derives read-only start/end times from the saved cut. The owner chooses direction, strength and a fixed anchor. Selecting or adjusting the effect creates no work until Create preview is pressed. A later timeline edit clears Dolly Zoom so the shot reference cannot migrate to unrelated footage.

The editing agent may select Dolly Zoom only for a stable, compositionally suitable shot. It is told to avoid fast motion, still images, edge text, overlays, existing camera treatments and uncertain anchors. Treatment review records the exact clip, direction, anchor and simulation limitation.

## Verification added

- The complete eight-gate source suite passes, including Python compilation, 120 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks.
- Model tests require the clip, direction and bounded anchor and reject Dolly parameters on other effects.
- Plan validation requires an exact complete video clip and rejects partial windows, still images, existing camera motion, tracked reframing and picture-layer conflicts.
- Timeline-retiming coverage proves that the shot-bound effect is cleared after cut changes.
- Filter-graph coverage checks the bounded time expression, scale amount, crop dimensions and fixed anchor.
- A real FFmpeg test verifies that a genuine source subject enlarges during a push while recorded audio remains continuous.
- Browser coverage confirms eligible clip labels, derived read-only timing, exact payload and no request before explicit submission.
- The synthetic effects preview exercises Dolly Zoom on its own complete source clip.
- The deployed-registry verifier expects version 10 and all eleven native effects without starting work.

Worker-container execution and real playback remain deployment acceptance checks because the development host does not provide the worker's Python dependencies or FFmpeg binary.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply Dolly Zoom to a stable 1–8 second medium or wide video clip with a clear central subject.
4. Compare push and pull at subtle, standard and strong strengths.
5. Check every edge for cropped text, hands, products or faces and confirm the fixed anchor remains visually convincing.
6. Confirm dialogue, music, source motion and captions remain synchronized.
7. Keep automatic agent use conservative until several differently composed shots pass playback review.

## Next slice

Completed in [Phase 32L — Effects Gallery](phase-32-effects-gallery.md): GM Studio now groups all eleven effects, exposes registry-backed usage guidance and explains cut-specific eligibility before submission.
