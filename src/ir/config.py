from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]


class ShotConfig(BaseModel):
    pyscenedetect_threshold: float = 27.0
    pyscenedetect_burst_merge_sec: float = 1.5
    min_shot_sec: float = 0.5


class KeyframeFilterConfig(BaseModel):
    min_sharpness: float = 120.0
    min_std: float = 8.0
    min_brightness: float = 20.0
    max_brightness: float = 235.0
    duplicate_distance: int = 5


class KeyframeConfig(BaseModel):
    short_side: int = 448
    jpeg_quality: int = 90
    long_shot_sec: float = 10.0
    every_sec: float = 5.0
    max_per_shot: int = 5
    filter: KeyframeFilterConfig = Field(default_factory=KeyframeFilterConfig)


class EmbedConfig(BaseModel):
    model: str = "sentence-transformers/clip-ViT-B-16"
    dim: int = 512
    batch_size: int = 128
    fp16: bool = True


class OcrConfig(BaseModel):
    engine: str | None = None
    language: str = "vi"
    min_conf: float = 0.5


class AsrConfig(BaseModel):
    model: str = "large-v3"
    compute_type: str = "float16"
    language: str = "vi"


class ObjectsConfig(BaseModel):
    model: str = "yolov8x.pt"
    conf: float = 0.25


class FaissConfig(BaseModel):
    type: Literal["flat", "hnsw", "ivfpq"] = "flat"
    hnsw_m: int = 32
    ef_search: int = 64


class Weights(BaseModel):
    dense: float = 1.0
    ocr: float = 0.5
    asr: float = 0.7
    obj: float = 0.4


class Boost(BaseModel):
    object: float = 1.2
    text_exact: float = 1.3


class SearchConfig(BaseModel):
    dense_k: int = 200
    top_k: int = 20
    rrf_k: int = 60
    temporal_window: int = 1
    weights: Weights = Field(default_factory=Weights)
    boost: Boost = Field(default_factory=Boost)


class TranslateConfig(BaseModel):
    enabled: bool = True
    model: str = "VietAI/envit5-translation"


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )


class AppConfig(BaseModel):
    corpus_dir: Path = Path("minibatch")
    artifacts_dir: Path = Path("artifacts")
    shot: ShotConfig = Field(default_factory=ShotConfig)
    keyframe: KeyframeConfig = Field(default_factory=KeyframeConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    objects: ObjectsConfig = Field(default_factory=ObjectsConfig)
    faiss: FaissConfig = Field(default_factory=FaissConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    translate: TranslateConfig = Field(default_factory=TranslateConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)

    @property
    def db_path(self) -> Path:
        return self.artifacts_dir / "metadata.sqlite"

    @property
    def keyframes_dir(self) -> Path:
        return self.artifacts_dir / "keyframes"

    @property
    def embeddings_path(self) -> Path:
        return self.artifacts_dir / "embeddings.f16.npy"

    @property
    def faiss_path(self) -> Path:
        return self.artifacts_dir / "faiss.index"


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def load_config(path: str | Path | None = None) -> AppConfig:
    source = Path(path or os.environ.get("IR_CONFIG", REPO_ROOT / "config.yaml")).resolve()
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    base = source.parent
    data["corpus_dir"] = _resolve(base, data.get("corpus_dir", "minibatch"))
    data["artifacts_dir"] = _resolve(base, data.get("artifacts_dir", "artifacts"))
    return AppConfig.model_validate(data)
