# Phase 32I — Rack Focus

Implemented in source on 2026-11-11. Container verification, deployment and real-footage quality acceptance remain pending.

## Purpose and limitation

Rack Focus begins the camera/transition pack with an honest local approximation. Without a depth map or lens metadata, GM Media Server cannot reproduce a true optical focus-plane change. This version therefore moves a sharp rectangular source window over a softly blurred copy of the same stable shot. It performs no depth detection, segmentation or subject tracking.

The limitation is visible in GM Studio, agent guidance, treatment review and the phase report. The effect should be rejected in playback if the window edge is distracting or the shot lacks two clear stable targets.

## Implemented result

Native effect registry version 8 adds **Rack Focus** with:

- a 1–4 second duration and 2 second default;
- subtle, standard and strong blur/window sizes;
- normalized start and end coordinates constrained to safe frame ranges;
- a minimum movement distance so a focus pull cannot silently become a static blur; and
- no generated picture, depth model, segmentation, tracking or additional model request.

The FFmpeg graph splits the original picture into its unchanged bed, blurred copy and sharp crop. The blurred layer fades in and out at the treatment boundaries. The sharp crop and its overlay position use the same bounded linear path, preserving source time and the complete audio branch. Dialogue captions are removed before this picture pass and restored above it afterward.

GM Studio exposes the four frame coordinates and explains that they are not tracked targets. Selection and adjustment remain local until Apply. The editing agent may use Rack Focus only on a stable shot with visual evidence for two clear targets, and must avoid fast motion, face close-ups and uncertain subjects. Treatment review records both coordinates and the simulation limitation.

## Verification added

- The complete eight-gate source suite passes, including Python compilation, 118 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks.
- Model tests reject missing, unsafe, too-close and misplaced focus coordinates.
- Registry tests cover all four numeric bounds and defaults.
- Filter-graph tests cover the three-way split, bounded interpolation, blur strength and crop size.
- A real FFmpeg test compares source/output regions to prove the moving window retains more detail than the blurred bed while audio remains continuous.
- Browser coverage confirms the limitation copy, default coordinates, exact payload and no request before Apply.
- The synthetic effects preview exercises Rack Focus on abstract source footage.
- The deployed-registry verifier expects version 8 and all nine native effects without starting work.

Worker-container execution and real playback remain deployment acceptance checks because the development host does not provide the worker's Python dependencies or FFmpeg binary.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply Rack Focus to a stable wide or medium shot with two clearly separated objects.
4. Compare subtle, standard and strong at phone and desktop sizes.
5. Reject the effect if its sharp-window boundary reads as a box rather than a focus change.
6. Confirm spoken audio, source motion and dialogue captions remain synchronized.
7. Keep automatic agent use conservative until several different real shots pass playback review.

## Next slice

Add **Paper Tear** as a true clip-boundary transition with recorded audio continuity, then prototype **Dolly Zoom** within the existing crop and motion limits.
