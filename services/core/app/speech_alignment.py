"""Offline English CTC alignment. The recognizer's words are never rewritten."""

import array
import gc
import math
import subprocess
from functools import lru_cache
from pathlib import Path


MODEL_REVISION = "22aad52d435eb6dbaf354bdad9b0da84ce7d6156"
SAMPLE_RATE = 16000


def ctc_spans(emissions, tokens, blank=0):
    """Viterbi over the standard blank/token CTC lattice, with repeat rules.

    Windows and transcripts are bounded by the caller. Rolling scores and
    byte-sized backpointers keep memory bounded without an extra ML runtime.
    Returned spans cover token evidence; safety margins still belong at cuts.
    """
    if not tokens or len(emissions) < len(tokens) + sum(a == b for a, b in zip(tokens, tokens[1:])):
        return None
    labels = [blank]
    for token in tokens:
        if token == blank:
            return None
        labels.extend((token, blank))
    count = len(labels)
    skip = [i > 1 and label != blank and label != labels[i - 2] for i, label in enumerate(labels)]
    previous = [-math.inf] * count
    previous[0] = 0.0
    trace = []
    for frame in emissions:
        current = [-math.inf] * count
        pointers = bytearray(count)
        for state, label in enumerate(labels):
            best = previous[state]
            if state and previous[state - 1] > best:
                best, pointers[state] = previous[state - 1], 1
            if skip[state] and previous[state - 2] > best:
                best, pointers[state] = previous[state - 2], 2
            current[state] = best + frame[label]
        previous = current
        trace.append(pointers)
    state = count - 1 if previous[-1] >= previous[-2] else count - 2
    if not math.isfinite(previous[state]):
        return None
    frames = [[] for _ in tokens]
    for index in range(len(emissions) - 1, -1, -1):
        if state % 2:
            frames[state // 2].append(index)
        state -= trace[index][state]
    if any(not values for values in frames):
        return None
    return [
        (min(values), max(values) + 1,
         math.exp(sum(emissions[t][token] for t in values) / len(values)))
        for token, values in zip(tokens, frames)
    ]


@lru_cache(maxsize=1)
def _model(path):
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    processor = Wav2Vec2Processor.from_pretrained(path, local_files_only=True)
    model = Wav2Vec2ForCTC.from_pretrained(path, local_files_only=True, use_safetensors=True,
        mask_time_prob=0.0, mask_feature_prob=0.0)
    return processor, model.eval()


class LocalAligner:
    def __init__(self, settings):
        self.settings = settings

    def __enter__(self):
        import torch
        from app.media_analysis import _whisper_model
        # Keep only the aligner on CUDA. The worker shares a small GPU with
        # encoding and visual indexing; model weights return to CPU on exit.
        _whisper_model.cache_clear()
        gc.collect()
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.processor, self.model = _model(str(self.settings.speech_alignment_model_path))
        self.device = "cuda" if self.settings.speech_alignment_device != "cpu" and torch.cuda.is_available() else "cpu"
        try:
            self.model.to(self.device)
        except RuntimeError:
            self.device = "cpu"
            self.model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        return self

    def __exit__(self, *_):
        import torch
        self.model.to("cpu")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def align(self, source: Path, start: float, end: float, words: list[str]):
        import torch
        import numpy as np
        result = subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.3f}",
            "-t", f"{end - start:.3f}", "-i", str(source), "-map", "0:a:0",
            "-vn", "-sn", "-dn", "-af", "aresample=16000:first_pts=0", "-ac", "1",
            "-f", "f32le", "-"], capture_output=True, check=True, timeout=15)
        samples = array.array("f", result.stdout)
        if len(samples) < SAMPLE_RATE // 10:
            return None
        audio = np.asarray(samples, dtype=np.float32)
        inputs = self.processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_values
        ids, word_tokens = [], []
        vocab = self.processor.tokenizer.get_vocab()
        separator = self.processor.tokenizer.word_delimiter_token
        for index, word in enumerate(words):
            if index:
                ids.append(vocab[separator])
            positions = []
            for letter in word.replace(" ", separator):
                if letter not in vocab:
                    return None
                positions.append(len(ids))
                ids.append(vocab[letter])
            word_tokens.append(positions)
        if len(ids) > 400:
            return None
        try:
            with torch.inference_mode():
                logits = self.model(inputs.to(self.device)).logits
                emissions = logits.log_softmax(-1)[0].float().cpu().tolist()
        except RuntimeError:
            if self.device == "cpu":
                raise
            self.model.to("cpu")
            self.device = "cpu"
            torch.cuda.empty_cache()
            with torch.inference_mode():
                emissions = self.model(inputs).logits.log_softmax(-1)[0].float().tolist()
        spans = ctc_spans(emissions, ids, self.model.config.pad_token_id)
        if spans is None:
            return None
        seconds = len(audio) / SAMPLE_RATE / len(emissions)
        return [{"start": start + min(spans[i][0] for i in indices) * seconds,
                 "end": start + max(spans[i][1] for i in indices) * seconds,
                 "score": sum(spans[i][2] for i in indices) / len(indices)}
                for indices in word_tokens]
