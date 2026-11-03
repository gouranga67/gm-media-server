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
