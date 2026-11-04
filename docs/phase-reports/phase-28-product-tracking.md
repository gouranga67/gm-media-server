# Phase 28 follow-up — Marked product follow

The owner can select up to two short main-picture video shots, see each shot's full first source frame, and mark a product region. This opt-in local pass preserves the approved cut, speech, captions, music and effects. It does not identify products automatically or extract their backgrounds.

## Using it

1. Open a ready edit and expand **Smart visual finishing**.
2. Choose **Choose a product shot**. Normal-speed video shots of 1–8 seconds are eligible. Clear manual camera anchors and shake reduction on that shot first. Single-face follow must be off in the saved preview before marking products.
3. Select the shot. The image is the full, rotated source frame at that shot's source start, with the same HDR conversion and dimensions used by the tracker. Tap a detailed product region and adjust its box width/height. Numeric centre controls also support keyboard use.
4. Choose **Add marked shot**, then **Create visual preview**. Adding/removing marks alone does not queue a job. No hosted AI request is made.
5. Watch the entire result. The saved report explains whether tracking was applied or existing framing retained. Tracking the product may move the speaker out of frame; choose framing to suit the story.

This follows small translations of a clearly visible, detailed region. It cannot promise reliable tracking through rotation, large scale changes, occlusion, blur, cuts or repeated lookalike products. It may decline those shots rather than produce a crop. It is a conservative first tracking tool, not general object recognition or a cutout model.

## Processing and replay

- At most two selected shots, each 1–8 seconds; 12-second total inspection budget and at most 6 seconds per child process. A timeout kills the process group, including its FFmpeg decoder.
- Original media is read without modification. Decode uses one CPU thread, at most 480 pixels on the long side and 8 sampled frames per second, at most 64 frames per shot. No proxy of uncertain crop/colour geometry is substituted.
- A fixed first-frame appearance template is matched within a small local search area. Low detail, weak correlation or ambiguous alternatives decline the whole shot. Lost targets are not reacquired globally. A saved crop path contains at most 33 points. The final constant crop interval is at most 250 ms; picture playback never freezes or retimes for tracking.
- Profiles are versioned, bound to the exact asset, source range and initial box, and cached using source identity and parameters. User/API callers cannot forge measurement profiles. Playback and final export replay the saved crop path without another analysis or model call. Reports mark actual framing application for the output aspect.
- Both speech and montage renderers use the path before the existing centre-fill crop and preset zoom. Crop-fit checks reserve room for that zoom; an unsafe aspect retains existing framing. This is main-picture framing only; B-roll layers keep their own treatment.
- Manual camera anchors, face follow and same-shot stabilization cannot compete with the product path. Arbitrary trims, reorders and hosted story revisions clear marks and paths. An approved shorter delivery variant retains tracking only on wholly unchanged prefix shots; its shortened final shot loses its mark.
- The source-frame endpoint requires the ready edit version, an eligible clip index and an attached source. It decodes one bounded private JPEG, uses no-store caching and accepts no arbitrary file path or seek time.

## Verification and remaining acceptance

Automated coverage exercises explicit selection and stale versions, coordinate bounds, limits/conflicts, source/seed binding, decline/replay/cache behaviour, decoder timeout cleanup, controlled translation, target loss and ambiguity. Actual CPU FFmpeg speech and montage renders keep a synthetic moving target visible and preserve identical decoded audio against the untracked baseline. The maximum saved path is parsed by FFmpeg. UI checks cover marking, removal, two-shot limits, frame errors and explicit submission.

The final backend run completed 740 checks: 739 passed and one unrelated disposable rclone retention integration was skipped because that temporary binary is unavailable. All ten product-tracking checks passed. The source suite passed eight gates, including 94 UI checks, web/agent TypeScript and the production web build. Chromium checks at 390px and 1280px verified source-frame marking, explicit submission, 44px controls and no horizontal overflow. Those browser requests used synthetic fixtures and made no production revisions or model calls.

Deploy with `sudo ./scripts/install-service.sh`, then run the read-only `python3 scripts/verify-phase28.py`. That check confirms the deployed capability contract, not subjective tracking quality. Real-footage playback acceptance remains open: test a moving labelled bottle, an occluded/rotating product, a shot with repeated jars, and both preview and final export. GPU/NVENC deployment is not established by the CPU fixture.
