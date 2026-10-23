import array
import math
import tempfile
import wave
from pathlib import Path
from typing import Any

from app.media_analysis import run_command


def analyze_music_beats(source: Path, duration_seconds: float, timeout: int) -> dict[str, Any]:
    """Estimate a bounded beat grid locally for cut alignment.

    This deliberately avoids a hosted music-analysis service. The result is an
    editing hint, not a claim about the track's published BPM.
    """

    with tempfile.TemporaryDirectory(prefix="gm-music-analysis-") as directory:
        decoded = Path(directory) / "mono.wav"
        completed = run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-c:a",
                "pcm_s16le",
                str(decoded),
            ],
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0 or not decoded.is_file():
            raise RuntimeError("music beat analysis could not decode the track")
        with wave.open(str(decoded), "rb") as audio:
            sample_rate = audio.getframerate()
            samples = array.array("h", audio.readframes(audio.getnframes()))

    window = 1024
    energies: list[float] = []
    for start in range(0, len(samples) - window + 1, window):
        block = samples[start : start + window]
        energies.append(math.sqrt(sum(sample * sample for sample in block) / window))
    if len(energies) < 32:
        raise RuntimeError("music track is too short for beat analysis")

    onsets = [0.0]
    for previous, current in zip(energies, energies[1:], strict=False):
        onsets.append(max(0.0, current - previous))
    frames_per_second = sample_rate / window
    minimum_lag = max(1, round(frames_per_second * 60 / 180))
    maximum_lag = max(minimum_lag + 1, round(frames_per_second * 60 / 60))
    best_lag = minimum_lag
    best_score = -1.0
    for lag in range(minimum_lag, min(maximum_lag, len(onsets) // 2) + 1):
        score = sum(onsets[index] * onsets[index - lag] for index in range(lag, len(onsets)))
        if score > best_score:
            best_score = score
            best_lag = lag
    bpm = 60 * frames_per_second / best_lag
    if bpm < 75:
        bpm *= 2
    elif bpm > 170:
        bpm /= 2
    beat_seconds = 60 / bpm
    phase_window = max(1, round(beat_seconds * frames_per_second))
    phase_frame = max(range(min(phase_window, len(onsets))), key=onsets.__getitem__)
    phase_seconds = phase_frame / frames_per_second
    limit = min(float(duration_seconds), 180.0)
    beats: list[float] = []
    beat = phase_seconds
    while beat <= limit + 0.001:
        beats.append(round(beat, 3))
        beat += beat_seconds
    return {"bpm": round(bpm, 2), "beat_grid_seconds": beats}
