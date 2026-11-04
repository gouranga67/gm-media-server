# Local visual-finishing dependencies and notices

The worker installs `opencv-python-headless==4.13.0.92`, a CPU-only build, and uses OpenCV’s `FaceDetectorYN` with the small YuNet 2023 model for optional face crop hints. This detects faces; it does not identify people or compute/store face-recognition embeddings. OpenCV’s wheel retains its own bundled license and third-party files.

The selected model and license are pinned to OpenCV Zoo commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`:

| File | Size / SHA-256 |
| --- | --- |
| `face_detection_yunet_2023mar.onnx` | 232,589 bytes; `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `LICENSE`, installed as `/models/YuNet-LICENSE` | `c83b8120c50ccbd4c4f96edf53141bdd566ebb8f8e9227e415326aa1b1aba958` |

The worker image fetches and checks both files at build time. Each inspector checks the model’s size/hash before loading it. An unavailable/mismatched model preserves the picture rather than downloading a replacement. The detector hash is part of the cache identity. The separate late build layer avoids invalidating existing cached speech/CLIP model downloads when adding this tool.

Primary references: [pinned package metadata and licensing](https://pypi.org/project/opencv-python-headless/4.13.0.92/), [OpenCV 4.13 Apache-2.0 license](https://github.com/opencv/opencv/blob/4.13.0/LICENSE), [pinned YuNet description and model compatibility](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/README.md), [model-directory MIT license](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/LICENSE), [OpenCV FaceDetectorYN documentation](https://docs.opencv.org/4.13.0/df/d20/classcv_1_1FaceDetectorYN.html). OpenCV 4.x uses the 2023 model here, not the newer OpenCV 5.x dynamic-shape export. No accuracy benchmark from those sources is claimed for GM Studio’s footage.

The YuNet notice, retained in the worker image:

```text
MIT License

Copyright (c) 2020 Shiqi Yu <shiqi.yu@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Temporary smoke-test image: the [scikit-image astronaut example](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) documents its NASA origin and public-domain status. It is not shipped as a library asset, used in production edits or uploaded to a hosted model. A synthetic moving composite was used to test sparse detection and crop motion, not to establish quality on real presenter footage.


## Selected-shot shake reduction

The stabilization follow-up uses the existing worker FFmpeg binary's native `deshake` filter. No model, package, downloaded media asset or separate motion-analysis pass is added to production. The worker build explicitly checks that the filter is available. See the [primary filter documentation](https://www.ffmpeg.org/ffmpeg-filters.html#deshake) for its translation-shake search and edge handling.

GM Studio fixes all filter arguments internally: a small bounded motion search, mirror edge handling, a fixed approximately 6% crop and restoration to output dimensions. The search is performed after resizing and frame-cadence normalization, before creative zooms. There is no configurable filter expression, output filename or GPU dependency. Existing source HDR-to-SDR conversion precedes this stage. The filter can mistake moving subjects for camera motion, and does not fix motion blur or rolling shutter; manual preview approval remains necessary.


## Experimental person-cutout comparison lab

The manually invoked lab uses OpenCV Zoo's PPHumanSeg 2023mar model at the same immutable repository revision `48b10fa505aeb51fbd127fc60a5c660040e823b7`. The model directory declares Apache-2.0 licensing. This is a person segmentation model, not a product-preserving matte model.

| File | Size / SHA-256 |
| --- | --- |
| `human_segmentation_pphumanseg_2023mar.onnx` | 6,163,938 bytes; `552d8a984054e59b5d773d24b9b12022b22046ceb2bbc4c9aaeaceb36a9ddf24` |
| `PPHumanSeg-LICENSE` | `d9cf3b547fa4232fb9285f2db52e909f10f00781aaf64a6d0bb90c55149f1363` |

The full, unmodified notice is retained in `services/core/model-assets/PPHumanSeg-LICENSE` and installed under `/models/PPHumanSeg-LICENSE`. A late worker build step verifies the notice, downloads at most the expected weight size plus one byte and rejects a mismatched hash. It does not invalidate the existing speech/CLIP model layers. Every lab invocation validates the weight size/hash again. Runtime inference has no network/model-download path.

The reference input contract is BGR-to-RGB, 192×192, normalized to [-1,1], with two output probabilities. The local implementation retains the foreground probability as a diagnostic alpha rather than claiming a learned fine-hair matte. Processing uses the existing CPU OpenCV package and makes no CUDA allocation. Ordinary editing does not invoke the lab.

Primary sources: [model README and licensing declaration](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/README.md), [Apache-2.0 notice](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/LICENSE), [Git LFS size/hash pointer](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/human_segmentation_pphumanseg_2023mar.onnx), [reference inference/preprocessing](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/human_segmentation_pphumanseg/pphumanseg.py).

The [cutout lab report](phase-reports/phase-28-cutout-lab.md) records the actual limitation: the tested candidate removed a held helmet. Model capability and speed are not recorded as a successful product-cutout acceptance result.
