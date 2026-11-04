# Phase 28 — Background-cutout comparison lab

This checkpoint implements a manually invoked, local person-segmentation prototype. It produces diagnostic comparisons without changing an edit plan, source file, caption, soundtrack or export. It is not an agent editing tool and does not enable automatic background removal.

## Important result

The small candidate is fast enough to investigate on this appliance, but it fails a held-object example. In a three-second translated NASA astronaut still, the model kept the person while removing the helmet she was holding. A manually chosen interior helmet region had 0% of its pixels classified as foreground. That is evidence against enabling this candidate for product-presenter reels, not proof about all possible footage.

The [recorded benchmark](phase-28-cutout-benchmark.json) processed 24 sampled frames at 480×480 in about 1.83 seconds using one CPU thread, with process peak RSS of approximately 275 MiB. This is an isolated host measurement using a translated still, not a production-container load test, natural-video benchmark or GPU comparison. The source file hash was unchanged. The current model remains rejected for automatic edit application; no quality approval is inferred from execution speed or mask stability numbers.

## Try a comparison after deployment

Run the normal installer first, then the read-only capability check:

```bash
cd /path/to/gm-media-server
sudo ./scripts/install-service.sh
python3 scripts/verify-phase28.py
```

Choose a ready job. Copy its full ID from the address after `/jobs/`. Replace `PASTE_JOB_ID_HERE` below with that ID; `--clip 1` means the first main-picture clip of the saved edit, not the first uploaded file:

```bash
sudo python3 scripts/preview-cutout.py PASTE_JOB_ID_HERE --clip 1
```

Optional arguments are `--offset 0.5` for a later point within the same shot and `--seconds 3` for a longer sample. Samples must be 0.5–3 seconds and stay inside a normal-speed video shot. The default is up to two seconds. Wait for the latest edit version to be ready first.

The command prints private links that open through GM Studio's existing Tailscale address:

- `comparison.mp4`: original picture, checkerboard cutout and mask side by side; silent, sampled at 8 fps.
- `contact.png`: first, middle and last sampled frames in the same layout.
- `matte.png`: the first sampled source frame with an experimental alpha channel.
- `report.json`: exact source/version binding, model identity, timing, memory measurements, warnings and review checklist.

These are comparison artifacts, not publishing outputs. They are based on the full source picture before the edit's crops, captions or effects. Watch hair, face edges, fingers, the complete held product and label, unwanted background islands, holes and temporal flicker. The segmentation-probability alpha is not a learned fine-hair matte. The sampled comparison does not establish full-frame-rate motion or audio-sync quality.

## Compute, storage and privacy

- One explicit CLI sample at a time; a nonblocking lock rejects concurrent prototype work. The ordinary worker, editor prompt, agent tools and upload pipeline do not call this prototype.
- A parent process enforces a 20-second inspection budget and kills the whole child/decoder process group on timeout. Failed partial output is cleaned up; completed comparisons are retained.
- At most 24 frames, 8 fps, three source seconds and 480 pixels on the long side. Model input is 192×192. OpenCV, decode and encode are limited to one CPU thread. CUDA/OpenCL are not used, leaving the existing GPU workload unchanged.
- The existing source rotation and HDR conversion precede segmentation. The comparison video explicitly converts RGB to limited-range BT.709 and tags it accordingly. This is not a new creative colour treatment.
- The worker includes the 6,163,938-byte PPHumanSeg 2023mar model and its Apache-2.0 notice. Both are pinned and checked; runtime inference never downloads a replacement. See [dependency records](../visual-finishing-dependencies.md).
- Results are cached by model/tool version, edit-plan hash, source identity and exact requested range. Repeated unchanged trials reuse the saved measurements. No hosted model receives a frame or transcript.
- Private read-only routes verify job/report binding, filenames, artifact sizes and hashes before serving results, including video byte ranges. No arbitrary source path or output filename is accepted by the wrapper or route. Reports cannot be changed into approved editing instructions by setting a flag.
- Files live under the existing media volume's `derived/cutout-lab` directory. They do not become library originals or new edit versions. Normal disk-capacity safeguards apply. There is no automatic pruning of completed comparisons in this checkpoint.

## Next quality gate

A production cutout tool needs a model or method that preserves the full presenter **and held objects**, representative full-motion tests, usable hair/hand edges, stable masks, measured appliance resource use under load, and a clear fallback to the original shot. A person-only mask's speed and a good torso silhouette do not satisfy that requirement. Real green-screen keying and geometric picture layers remain the dependable existing options.

This delivery intentionally stops at the comparison boundary. Adding an Apply button or exposing the mask to the editing agent before passing that gate would make otherwise good edits worse.

## Verification scope

Focused checks cover pinned weights/license, correct RGB normalization, malformed model output, sample bounds, immutable sources, cache replay, artifact hashes, private route validation, actual video range delivery, concurrency, subprocess timeout cleanup, argument safety and sanitized wrapper failures. Actual CPU inference and FFmpeg encoding produce a playable silent comparison and a four-channel PNG. An in-memory ASGI test exercises the native framework's request validation and ranged file delivery with disposable files and a fake job lookup.

Final development verification: 753 backend tests ran, with 752 passing and one unrelated rclone skip; all 13 cutout-lab tests passed. The source suite passed all eight gates, including 94 UI checks, TypeScript checks and the production web build. A pre-existing render test now measures a small colour patch instead of one pixel on a compressed colour boundary; its framing, dissolve and audio checks passed with both real NVENC and the CPU encoder fallback. The public-release audit also checks the final documentation.

Production Docker rebuild, owner-footage assessment and appliance load acceptance remain pending. No production edit, social post or hosted editing request was started during development verification. No database migration is needed.

Primary references: [model description](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/README.md), [pinned model license](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/LICENSE), [reference preprocessing](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/pphumanseg.py), [NASA sample provenance and public-domain status](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut). The sample is temporary test material and is not shipped in the user's library.
