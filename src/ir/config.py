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
    min_std: float = 8.0
    min_brightness: float = 20.0
    max_brightness: float = 235.0
    duplicate_distance: int = 5
    metric_width: int = 320


class FollowConfig(BaseModel):
    step_sec: float = 0.5
    max_frames: int = 8
    window_sec: float = 1.0
    short_side: int = 320
    quality: int = 75
    image_format: Literal["webp", "jpeg"] = "webp"
    bidirectional: bool = True


class KeyframeConfig(BaseModel):
    short_side: int = 448
    jpeg_quality: int = 90
    every_sec: float = 4.0
    candidate_step_sec: float = 0.25
    min_gap_sec: float = 1.0
    filter: KeyframeFilterConfig = Field(default_factory=KeyframeFilterConfig)
    follow: FollowConfig = Field(default_factory=FollowConfig)


class IngestConfig(BaseModel):
    workers: int = 1
    decode_threads: int = 2


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


class DresConfig(BaseModel):
    base_url: str = "https://eventretrieval.one"
    session_id: str | None = None
    evaluation_id: str | None = None
    timeout_sec: float = 15.0


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )


class AppConfig(BaseModel):
    corpus_dir: Path = Path("minibatch")
    artifacts_dir: Path = Path("artifacts")
    state_dir: Path | None = None
    shot: ShotConfig = Field(default_factory=ShotConfig)
    keyframe: KeyframeConfig = Field(default_factory=KeyframeConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    objects: ObjectsConfig = Field(default_factory=ObjectsConfig)
    faiss: FaissConfig = Field(default_factory=FaissConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    translate: TranslateConfig = Field(default_factory=TranslateConfig)
    dres: DresConfig = Field(default_factory=DresConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)

    @property
    def state_root(self) -> Path:
        if self.state_dir is not None:
            return self.state_dir
        return self.artifacts_dir.parent / f"{self.artifacts_dir.name}_state"

    @property
    def db_path(self) -> Path:
        return self.state_root / "metadata.sqlite"

    @property
    def keyframes_dir(self) -> Path:
        return self.artifacts_dir / "keyframes"

    @property
    def keyframes_manifest_path(self) -> Path:
        return self.artifacts_dir / "manifest.jsonl"

    @property
    def follow_frames_dir(self) -> Path:
        return self.state_root / "follow_frames"

    @property
    def embeddings_dir(self) -> Path:
        return self.state_root / "embed"

    @property
    def embeddings_path(self) -> Path:
        return self.embeddings_dir / "embeddings.f16.npy"

    @property
    def faiss_path(self) -> Path:
        return self.embeddings_dir / "faiss.index"

    @property
    def id_map_path(self) -> Path:
        return self.embeddings_dir / "id_map.npy"

    @property
    def manifest_path(self) -> Path:
        return self.embeddings_dir / "manifest.json"

    @property
    def shards_dir(self) -> Path:
        return self.embeddings_dir / "shards"


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def load_config(path: str | Path | None = None) -> AppConfig:
    source = Path(path or os.environ.get("IR_CONFIG", REPO_ROOT / "config.yaml")).resolve()
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    base = source.parent
    data["corpus_dir"] = _resolve(base, data.get("corpus_dir", "minibatch"))
    data["artifacts_dir"] = _resolve(base, data.get("artifacts_dir", "artifacts"))
    if data.get("state_dir"):
        data["state_dir"] = _resolve(base, data["state_dir"])
    return AppConfig.model_validate(data)
