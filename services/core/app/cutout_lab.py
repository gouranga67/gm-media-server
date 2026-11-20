"""Manual person-segmentation comparisons, excluded from production editing.

The appearance of hair, hands and held products is a human acceptance gate.
Segmentation probabilities are not a learned hair matte or a quality score.
No model call, original rewrite, edit-plan update or final export is performed.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "person_cutout_lab_v1"
MODEL_FILE = "human_segmentation_pphumanseg_2023mar.onnx"
MODEL_SHA256 = "552d8a984054e59b5d773d24b9b12022b22046ceb2bbc4c9aaeaceb36a9ddf24"
MODEL_SIZE = 6163938
MODEL_PATH = Path("/models") / MODEL_FILE
FPS, MAX_SECONDS, MAX_FRAMES, BUDGET_SECONDS = 8, 3, 24, 20
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
ARTIFACT_TYPES = {"comparison.mp4": "video/mp4", "contact.png": "image/png", "matte.png": "image/png"}
REVIEW_ITEMS = ["Hair and face edges", "Both hands and fingers", "Entire held product and its label",
    "Background holes and unwanted objects", "Temporal flicker through the whole sample", "Local processing cost"]


class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    job_id: UUID
    edit_version: int = Field(strict=True, gt=0)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clip_index: int = Field(strict=True, ge=0, le=47)
    asset_id: UUID
    start: float = Field(ge=0, le=86400)
    end: float = Field(gt=0, le=86520)

    @model_validator(mode="after")
    def bounded(self):
        if not .5 <= round(self.end - self.start, 6) <= MAX_SECONDS:
            raise ValueError("choose a source sample of 0.5–3 seconds")
        return self


def select_sample(job_id, row, clip_number, offset=0., seconds=None):
    from app.edit_plan import document_sha256
    if not row or row.get("status") != "ready" or not row.get("document"):
        raise ValueError("wait for the latest edit version to be ready before testing a cutout")
    if type(clip_number) is not int or not 1 <= clip_number <= 48:
        raise ValueError("clip numbers start at 1 and cannot exceed 48")
    document = row["document"]
    clips = document.get("clips", [])
    if clip_number > len(clips):
        raise ValueError("choose a main-picture clip from the saved edit")
    clip = clips[clip_number - 1]
    span = float(clip["source_out"] - clip["source_in"])
    if clip.get("media_kind", "video") != "video" or abs(float(clip.get("duration", span)) - span) > .001:
        raise ValueError("cutout comparisons need normal-speed video, not photos, held or retimed picture")
    if not math.isfinite(offset) or offset < 0 or offset >= span:
        raise ValueError("sample offset must be inside the selected shot")
    duration = min(2., span - offset) if seconds is None else seconds
    if not math.isfinite(duration) or offset + duration > span + .000001:
        raise ValueError("the requested sample extends beyond the selected shot")
    return Sample(job_id=job_id, edit_version=row["version"], plan_sha256=document_sha256(document),
        clip_index=clip_number - 1, asset_id=clip["asset_id"], start=float(clip["source_in"]) + offset,
        end=float(clip["source_in"]) + offset + duration)


def checked_model(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != MODEL_SIZE or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("the pinned cutout prototype model is unavailable; deploy the new worker build first")
    return path


def validate_measurements(metrics, sample):
    duration = round(sample.end - sample.start, 6)
    if not isinstance(metrics, dict) or type(metrics.get("sampled_frames")) is not int or not math.floor(duration * FPS) <= metrics["sampled_frames"] <= min(MAX_FRAMES, math.ceil(duration * FPS)) or metrics.get("sample_fps") != FPS or metrics.get("backend") != "opencv_cpu" or metrics.get("threads") != 1:
        raise ValueError("invalid cutout measurements")
    seconds = metrics.get("processing_seconds")
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= BUDGET_SECONDS:
        raise ValueError("invalid cutout processing duration")


def open_model(path):
    import cv2
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    model = cv2.dnn.readNet(str(checked_model(path)))
    model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return model


def segment(model, frame):
    """Follow the pinned model's RGB, 192x192, [-1,1] input contract."""
    import cv2
    import numpy as np
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    normalized = cv2.resize(rgb, (192, 192)).astype(np.float32) / 127.5 - 1
    model.setInput(cv2.dnn.blobFromImage(normalized))
    scores = model.forward()
    if scores.shape != (1, 2, 192, 192) or not np.isfinite(scores).all() or scores.min() < 0 or scores.max() > 1 or not np.allclose(scores.sum(axis=1), 1, atol=.001):
        raise ValueError("unexpected person-segmentation probabilities")
    probability = cv2.resize(scores[0, 1], (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.rint(probability * 255).astype(np.uint8)


def comparison_panel(frame, alpha, source_time, background=None):
    import cv2
    import numpy as np
    height, width = alpha.shape
    yy, xx = np.indices((height, width))
    board = background
    if board is None:
        board = np.where((xx // 16 + yy // 16) % 2, 180, 225).astype(np.uint8)
        board = np.repeat(board[:, :, None], 3, axis=2)
    if board.shape != frame.shape:
        raise ValueError("replacement background dimensions do not match the sample")
    weight = alpha[:, :, None].astype(np.float32) / 255
    composite = np.rint(frame * weight + board * (1 - weight)).astype(np.uint8)
    mask = np.repeat(alpha[:, :, None], 3, axis=2)
    panel = np.full((height + 28, width * 3, 3), 245, np.uint8)
    panel[28:] = np.concatenate((frame, composite, mask), axis=1)
    middle_title = "Chosen background" if background is not None else "Cutout test"
    for i, title in enumerate(("Original", middle_title, "Mask")):
        cv2.putText(panel, f"{title} {source_time:.2f}s", (i * width + 4, 18), cv2.FONT_HERSHEY_SIMPLEX,
            min(.4, width / 340), (35, 45, 50), 1, cv2.LINE_AA)
    return panel


def decode_background(source, width, height):
    import numpy as np
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(source),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
        "-frames:v", "1", "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=6, check=True)
    expected = width * height * 3
    if len(result.stdout) != expected:
        raise ValueError("replacement background could not be decoded")
    return np.frombuffer(result.stdout, np.uint8).reshape(height, width, 3)


def render_comparison(source, sample, model_path, output, background_source=None):
    import cv2
    import numpy as np
    from app.product_tracking import decoder
    started = time.monotonic()
    model = open_model(model_path)
    command, original_dimensions, (width, height) = decoder(source, sample.start, sample.end - sample.start)
    decoded = subprocess.run(command + ["-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=6, check=True)
    count = len(decoded.stdout) // (width * height * 3)
    if not math.floor((sample.end - sample.start) * FPS) <= count <= MAX_FRAMES:
        raise ValueError("incomplete sample decode")
    frames = np.frombuffer(decoded.stdout, np.uint8).reshape(count, height, width, 3)
    background = decode_background(background_source, width, height) if background_source else None
    decode_seconds = time.monotonic() - started
    panels, coverages, uncertainty, changes = [], [], [], []
    previous = None
    inference_start = time.monotonic()
    for index, frame in enumerate(frames):
        alpha = segment(model, frame)
        coverages.append(float(np.mean(alpha >= 128)))
        uncertainty.append(float(np.mean((alpha > 25) & (alpha < 230))))
        if previous is not None:
            changes.append(float(np.mean((alpha >= 128) != (previous >= 128))))
        panels.append(comparison_panel(frame, alpha, sample.start + index / FPS, background))
        if index == 0:
            rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            rgba[:, :, 3] = alpha
            if not cv2.imwrite(str(output / "matte.png"), rgba):
                raise ValueError("could not write prototype alpha image")
        previous = alpha
    inference_seconds = time.monotonic() - inference_start
    samples = sorted({0, count // 2, count - 1})
    if not cv2.imwrite(str(output / "contact.png"), np.concatenate([panels[i] for i in samples], axis=0)):
        raise ValueError("could not write comparison contact sheet")
    encode_start = time.monotonic()
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width * 3}x{height + 28}", "-r", str(FPS), "-i", "pipe:0",
        "-an", "-filter_threads", "1", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=limited",
        "-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-movflags", "+faststart", str(output / "comparison.mp4")], input=b"".join(p.tobytes() for p in panels),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=6, check=True)
    warnings = ["Sampled silent comparison only. This person mask may remove held products and fine hair.",
        "Mask changes also reflect normal motion; the measurements do not certify flicker or visual quality."]
    if min(coverages) < .01 or max(coverages) > .98:
        warnings.append("At least one sample has almost no person or almost no background; inspect the mask carefully.")
    return {"source_dimensions": list(original_dimensions), "analysis_dimensions": [width, height], "sampled_frames": count,
        "sample_fps": FPS, "sample_source_times": [round(sample.start + i / FPS, 4) for i in samples],
        "backend": "opencv_cpu", "opencv_version": cv2.__version__, "threads": 1,
        "decode_and_model_seconds": round(decode_seconds, 4), "inference_and_panels_seconds": round(inference_seconds, 4),
        "encode_seconds": round(time.monotonic() - encode_start, 4), "processing_seconds": round(time.monotonic() - started, 4),
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "subprocess_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "foreground_fraction_range": [round(min(coverages), 4), round(max(coverages), 4)],
        "uncertain_pixel_fraction_mean": round(float(np.mean(uncertainty)), 4),
        "uncompensated_mask_change_max": round(max(changes, default=0), 4), "warnings": warnings}


def render_full_matte(source, model_path, destination, *, fps, width, height, duration):
    """Create a frame-aligned lossless grayscale matte for an already assembled reel.

    The caller supplies picture-only video with the exact crop, timing and camera
    treatments used by the final render. Captions and overlays are deliberately
    applied later, after compositing, so the person model cannot erase them.
    """
    import cv2
    import numpy as np
    source = Path(source)
    destination = Path(destination)
    if not source.is_file() or not 1 <= fps <= 60 or not 1 <= duration <= 120:
        raise ValueError("invalid full-reel cutout input")
    model = open_model(model_path)
    capture = cv2.VideoCapture(str(source))
    expected_frames = round(duration * fps)
    temporary = destination.with_name(f".{destination.name}.part.mkv")
    temporary.unlink(missing_ok=True)
    encoder = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "ffv1", "-level", "3",
        "-pix_fmt", "gray", str(temporary),
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    frames = 0
    started = time.monotonic()
    try:
        if not capture.isOpened() or encoder.stdin is None:
            raise ValueError("the assembled reel could not be opened for person isolation")
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[:2] != (height, width):
                raise ValueError("the assembled reel changed dimensions during person isolation")
            alpha = segment(model, frame)
            # Preserve the probability-shaped edge seen in the accepted sample.
            # Only lock near-certain pixels to remove compression shimmer.
            alpha = np.where(alpha <= 3, 0, np.where(alpha >= 252, 255, alpha)).astype(np.uint8)
            encoder.stdin.write(alpha.tobytes())
            frames += 1
            if frames > expected_frames + 1:
                raise ValueError("the assembled reel exceeded its expected frame count")
        encoder.stdin.close()
        encoder.stdin = None
        try:
            _, errors = encoder.communicate(timeout=max(30, min(600, round(duration * 5))))
        except subprocess.TimeoutExpired:
            encoder.kill()
            _, errors = encoder.communicate()
            raise ValueError("full-reel person isolation exceeded its processing budget")
        if encoder.returncode or not temporary.is_file() or temporary.stat().st_size <= 0:
            detail = errors.decode("utf-8", "replace")[-240:] if errors else ""
            raise ValueError(f"the full-reel person matte could not be encoded: {detail}")
        if abs(frames - expected_frames) > 1:
            raise ValueError("the full-reel person matte is incomplete")
        temporary.chmod(0o440)
        os.replace(temporary, destination)
        return {
            "frames": frames,
            "fps": fps,
            "width": width,
            "height": height,
            "processing_seconds": round(time.monotonic() - started, 3),
            "model": "PPHumanSeg 2023mar",
            "model_sha256": MODEL_SHA256,
            "backend": "opencv_cpu",
        }
    except (BrokenPipeError, OSError) as error:
        raise ValueError("full-reel person isolation stopped before completion") from error
    finally:
        capture.release()
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        temporary.unlink(missing_ok=True)


def lab_root(media_root):
    root = Path(media_root).resolve()
    target = (root / "derived" / "cutout-lab").resolve()
    if not target.is_relative_to(root):
        raise ValueError("cutout comparison storage is outside the media root")
    return target


@contextmanager
def lab_slot(root):
    root.mkdir(parents=True, exist_ok=True)
    # Never queue unbounded prototype work alongside real edit jobs.
    with os.fdopen(os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another cutout comparison is running; try again when it finishes")
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_report(media_root, job_id, key):
    from app.media_analysis import resolve_source
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("invalid cutout comparison identifier")
    relative = f"derived/cutout-lab/{UUID(str(job_id))}/{key}/report.json"
    path = resolve_source(Path(media_root), relative)
    if path.stat().st_size > 32768:
        raise ValueError("invalid cutout comparison report")
    report = json.loads(path.read_bytes())
    if not isinstance(report, dict) or report.get("version") != VERSION or report.get("model_sha256") != MODEL_SHA256 or report.get("cache_key") != key or not isinstance(report.get("sample"), dict) or report["sample"].get("job_id") != str(job_id) or report.get("eligible_for_edit_application") is not False or report.get("quality_approved") is not False or report.get("hosted_model_calls") != 0 or not isinstance(report.get("artifacts"), dict) or set(report["artifacts"]) != set(ARTIFACT_TYPES):
        raise ValueError("invalid cutout comparison binding")
    sample = Sample.model_validate(report["sample"])
    validate_measurements(report.get("metrics"), sample)
    for item in report["artifacts"].values():
        if not isinstance(item, dict) or type(item.get("bytes")) is not int or not 0 < item["bytes"] <= MAX_ARTIFACT_BYTES or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["sha256"]):
            raise ValueError("invalid cutout artifact metadata")
    return path, report


def artifact_path(media_root, job_id, key, filename):
    from app.media_analysis import resolve_source
    report_path, report = read_report(media_root, job_id, key)
    if filename == "report.json":
        return report_path, "application/json"
    if filename not in ARTIFACT_TYPES:
        raise ValueError("unknown cutout comparison artifact")
    relative = str((report_path.parent / filename).relative_to(Path(media_root).resolve()))
    path = resolve_source(Path(media_root), relative)
    expected = report["artifacts"][filename]
    if not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES or path.stat().st_size != expected["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("cutout comparison artifact is incomplete or changed")
    return path, ARTIFACT_TYPES[filename]


def create_comparison(source, sample, settings, *, background_source=None, background_asset_id=None):
    from app.media_analysis import ensure_capacity
    sample = Sample.model_validate(sample)
    model_path = checked_model(getattr(settings, "cutout_model_path", MODEL_PATH))
    stat = Path(source).stat()
    background_identity = None
    if background_source is not None:
        background_stat = Path(background_source).stat()
        background_identity = [str(background_source), background_stat.st_size, background_stat.st_mtime_ns,
            str(UUID(str(background_asset_id)))]
    identity = [VERSION, MODEL_SHA256, sample.model_dump(mode="json"), str(source), stat.st_size, stat.st_mtime_ns,
        background_identity]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    root = lab_root(settings.media_root)
    with lab_slot(root):
        job_root = (root / str(sample.job_id)).resolve()
        if not job_root.is_relative_to(root):
            raise ValueError("cutout comparison storage is outside the media root")
        destination = job_root / key
        if destination.exists():
            for filename in ARTIFACT_TYPES:
                artifact_path(settings.media_root, sample.job_id, key, filename)
            _, report = read_report(settings.media_root, sample.job_id, key)
            return report  # Reuse measurements, never rejudge or overwrite a saved trial.
        ensure_capacity(settings)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".work-", dir=destination.parent))
        process = None
        try:
            process = subprocess.Popen([sys.executable, "-m", "app.cutout_lab", "--inspect"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "-1"})
            try:
                output, _ = process.communicate(json.dumps(dict(source=str(source), sample=sample.model_dump(mode="json"),
                    model=str(model_path), output=str(temporary),
                    background=str(background_source) if background_source is not None else None)).encode(), timeout=BUDGET_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
                raise ValueError("cutout comparison exceeded its 20-second budget; the edit is unchanged")
            if process.returncode:
                raise ValueError("local cutout comparison could not finish; the edit is unchanged")
            metrics = json.loads(output)
            validate_measurements(metrics, sample)
            artifacts = {}
            for name in ARTIFACT_TYPES:
                path = temporary / name
                if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES:
                    raise ValueError("incomplete cutout comparison")
                artifacts[name] = dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            report = dict(version=VERSION, model="PPHumanSeg 2023mar", model_sha256=MODEL_SHA256, model_license="Apache-2.0",
                cache_key=key, sample=sample.model_dump(mode="json"), metrics=metrics, artifacts=artifacts,
                background_asset_id=str(UUID(str(background_asset_id))) if background_asset_id is not None else None,
                comparison_kind="chosen_background" if background_source is not None else "checkerboard",
                eligible_for_edit_application=False, quality_approved=False, human_review_items=REVIEW_ITEMS,
                alpha_kind="segmentation_probability_not_hair_matting", hosted_model_calls=0,
                original_files_changed=0, edit_versions_created=0, final_exports_created=0)
            (temporary / "report.json").write_text(json.dumps(report, allow_nan=False))
            temporary.rename(destination)
            return report
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description="Make a sampled cutout comparison; never applies it to an edit.")
    parser.add_argument("--job", type=UUID, required=True)
    parser.add_argument("--clip", type=int, required=True, help="main-picture clip number, starting at 1")
    parser.add_argument("--offset", type=float, default=0)
    parser.add_argument("--seconds", type=float, default=None)
    args = parser.parse_args()
    from app.config import get_settings
    from app.database import connection
    from app.editor_context import build_editor_context, resolve_internal_asset_source
    settings = get_settings()
    with connection() as database:
        row = database.execute("""SELECT r.version,r.status,p.document FROM edit_runs r LEFT JOIN edit_plans p ON p.id=r.edit_plan_id
            WHERE r.job_id=%s ORDER BY r.version DESC LIMIT 1""", (args.job,)).fetchone()
    sample = select_sample(args.job, row, args.clip, args.offset, args.seconds)
    context = build_editor_context(args.job, include_internal_paths=True)
    asset = next(a for a in context["assets"] if str(a["asset_id"]) == str(sample.asset_id))
    report = create_comparison(resolve_internal_asset_source(settings, asset), sample, settings)
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--inspect"]:
            payload = json.loads(sys.stdin.read(8192))
            result = render_comparison(Path(payload["source"]), Sample.model_validate(payload["sample"]), Path(payload["model"]),
                Path(payload["output"]), Path(payload["background"]) if payload.get("background") else None)
            print(json.dumps(result, allow_nan=False))
        else:
            main()
    except (OSError, ValueError, LookupError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Cutout comparison did not finish: {str(error)[:200]}", file=sys.stderr)
        raise SystemExit(1)
