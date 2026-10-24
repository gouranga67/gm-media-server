"""Private GPU service for deterministic CLIP image/text embeddings."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator
from transformers import CLIPModel, CLIPProcessor

from app.config import get_settings
from app.media_analysis import resolve_source
from app.visual_index import (
    VISUAL_MODEL_ID,
    VISUAL_MODEL_REVISION,
    VISUAL_VECTOR_DIMENSION,
)


class TextEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=160)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized


class ImageEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paths: list[str] = Field(min_length=1, max_length=32)


class Encoder:
    def __init__(self) -> None:
        settings = get_settings()
        model_path = str(settings.visual_model_path)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = CLIPProcessor.from_pretrained(model_path, local_files_only=True)
        self.model = CLIPModel.from_pretrained(model_path, local_files_only=True)
        self.model.eval().to(self.device)
        self.lock = Lock()

    @staticmethod
    def _values(tensor: torch.Tensor) -> list[list[float]]:
        normalized = torch.nn.functional.normalize(tensor.float(), p=2, dim=-1)
        return normalized.detach().cpu().tolist()

    def text(self, value: str) -> list[float]:
        with self.lock:
            inputs = self.processor(text=[value], return_tensors="pt", padding=True)
            inputs = {key: item.to(self.device) for key, item in inputs.items()}
            with torch.inference_mode():
                features = self.model.get_text_features(**inputs)
        return self._values(features)[0]

    def images(self, paths: list[Path]) -> list[list[float]]:
        opened: list[Image.Image] = []
        try:
            for path in paths:
                with Image.open(path) as image:
                    image.load()
                    opened.append(image.convert("RGB"))
            with self.lock:
                inputs = self.processor(images=opened, return_tensors="pt")
                inputs = {key: item.to(self.device) for key, item in inputs.items()}
                with torch.inference_mode():
                    features = self.model.get_image_features(**inputs)
            return self._values(features)
        finally:
            for image in opened:
                image.close()


encoder: Encoder | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global encoder
    encoder = Encoder()
    yield
    encoder = None


app = FastAPI(title="GM Visual Encoder", docs_url=None, redoc_url=None, lifespan=lifespan)


def _encoder() -> Encoder:
    if encoder is None:
        raise HTTPException(status_code=503, detail="visual encoder is loading")
    return encoder


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"service": "visual-encoder", "status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, Any]:
    active = _encoder()
    return {
        "service": "visual-encoder",
        "status": "ready",
        "model": VISUAL_MODEL_ID,
        "revision": VISUAL_MODEL_REVISION,
        "dimension": VISUAL_VECTOR_DIMENSION,
        "device": active.device,
    }


@app.post("/embed/text")
def embed_text(payload: TextEmbeddingRequest) -> dict[str, Any]:
    return {
        "model": VISUAL_MODEL_ID,
        "revision": VISUAL_MODEL_REVISION,
        "embedding": _encoder().text(payload.text),
    }


@app.post("/embed/images")
def embed_images(payload: ImageEmbeddingRequest) -> dict[str, Any]:
    settings = get_settings()
    paths: list[Path] = []
    for item in payload.paths:
        path = resolve_source(settings.media_root, item)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="one or more visual frames are missing")
        paths.append(path)
    return {
        "model": VISUAL_MODEL_ID,
        "revision": VISUAL_MODEL_REVISION,
        "embeddings": _encoder().images(paths),
    }
