# Phase 28 follow-up — selected-shot shake reduction

The visual finishing panel now lets the owner choose a few genuinely shaky main-picture clips and create a separate local preview. The same bounded tool is available to the agent through `inspect_edit_tools` and `apply_finishing`, only on explicit request. It does not change the existing story editor or enable itself on new jobs.

## Behaviour and bounds

- Up to four distinct 1–8 second normal-speed video clips per edit: at most 32 seconds of selected picture processed per render. Photos, retimed/held picture, missing indexes, duplicate indexes and manually anchored shots are rejected. Single-face follow must be off.
- The native FFmpeg translation-shake filter operates after HDR conversion, resizing and cadence normalization, before creative zooms. A fixed approximately 6% edge crop removes most correction borders. Audio filters, source ranges, captions and timeline clocks are unchanged. Separate B-roll overlays retain their own treatment.
- The worker build checks native filter availability. No new production dependency/model, source rewrite, cached reanalysis or hosted model call is added. All filter arguments are internal constants; clients supply only bounded indexes.
- Saved finishing settings, manifest and treatment timeline disclose the selected clips. Reports explicitly do not certify visual quality. Shake, pan and moving-subject results need human playback approval; blur and rolling shutter are not repaired.
- Arbitrary timeline/source edits and hosted story revisions clear old selected indexes. Approved prefix delivery variants retain surviving eligible choices, without extending a correction onto unrelated content. Off-by-default serialization preserves old plan hashes and the hosted editor schema.

## Verification

The backend run completed 730 tests: 729 passed and one unrelated rclone-dependent retention integration check was skipped because that temporary binary was unavailable after reboot. All six new stabilization tests passed, including actual speech and montage renders. A controlled textured moving-camera fixture reduced measured translation jitter in both paths while retaining identical decoded audio and exact 30fps frame counts from 60fps input. This proves technical behaviour on the fixture, not aesthetic improvement on natural footage.

The source suite passed eight gates, including 91 UI interactions, TypeScript, public audit and production web build. Focused agent-tool TypeScript also passed after exposing the bounded setting. UI tests cover no automatic load/application, explicit selection/submission, disabled ineligible clips, four-clip limits, face-follow conflict, clearing only on submit and preserved unrelated finishing.

Phone/desktop layout checks use synthetic intercepted API responses, without production jobs or paid requests. Real-footage shake/crop and downloaded-final acceptance remain pending. See [testing-plan.md](../testing-plan.md). Deploy with the normal service installer, then run `python3 scripts/verify-phase28.py`; no new database migration is required for this follow-up.
