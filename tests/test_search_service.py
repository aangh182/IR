from __future__ import annotations

import json
from contextlib import closing

import faiss
import numpy as np
import pytest

import ir.search.service as service_module
from ir.config import AppConfig, EmbedConfig, EmbedProfile
from ir.search.service import SearchService
from ir.store.db import (
    connect,
    init_db,
    insert_follow_frame,
    insert_keyframe,
    set_keyframe_objects,
    upsert_video,
)
from ir.types import FollowFrame, Keyframe, Video


class _FakeEncoder:
    def __init__(self, vector: np.ndarray) -> None:
        self.vector = vector
        self.inputs: list[str] = []

    def encode(self, text: str) -> np.ndarray:
        self.inputs.append(text)
        return self.vector


class _Translator:
    def __init__(self, output: str | None = None) -> None:
        self.output = output
        self.inputs: list[str] = []

    def translate(self, text: str) -> str:
        self.inputs.append(text)
        return self.output if self.output is not None else text


def _write_embeddings(root, vectors: np.ndarray, ids: np.ndarray, model: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    faiss.normalize_L2(vectors)

    np.save(root / "embeddings.f16.npy", vectors.astype(np.float16))
    np.save(root / "id_map.npy", ids.astype(np.int64))

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(root / "faiss.index"))

    (root / "manifest.json").write_text(
        json.dumps({"model": model, "count": len(ids), "dim": vectors.shape[1]}),
        encoding="utf-8",
    )


def test_search_dedups_by_shot_and_builds_payload(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        corpus_dir=tmp_path / "corpus",
        artifacts_dir=tmp_path / "artifacts",
    )
    init_db(cfg.db_path)

    with closing(connect(cfg.db_path)) as conn:
        upsert_video(
            conn,
            Video(
                video_id="V1",
                path=str(tmp_path / "V1.mp4"),
                duration_ms=60_000,
                fps=25.0,
            ),
        )
        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('V1', 0, 0, 0, 30000), ('V1', 0, 1, 30000, 60000)"
        )
        conn.commit()

        uids = [
            insert_keyframe(
                conn,
                Keyframe(
                    video_id="V1",
                    shot_idx=shot_idx,
                    kf_idx=kf_idx,
                    ts_ms=ts_ms,
                    path=f"keyframes/V1/g0/{shot_idx:06d}_{kf_idx:03d}.jpg",
                ),
            )
            for shot_idx, kf_idx, ts_ms in ((0, 0, 5000), (0, 1, 8000), (1, 0, 40000))
        ]

        for frame_idx, ts_ms in enumerate((4500, 5500)):
            insert_follow_frame(
                conn,
                FollowFrame(
                    video_id="V1",
                    shot_idx=0,
                    kf_idx=0,
                    frame_idx=frame_idx,
                    ts_ms=ts_ms,
                    path=f"follow_frames/V1/g0/000000_000_{frame_idx:03d}.jpg",
                ),
            )

    vectors = np.zeros((3, cfg.embed.dim), dtype=np.float32)
    vectors[0, 0] = 1.0
    vectors[1, 0] = 0.6
    vectors[1, 1] = 0.8
    vectors[2, 1] = 1.0
    _write_embeddings(cfg.embeddings_dir, vectors, np.asarray(uids), cfg.embed.model)

    query = vectors[0].copy()
    faiss.normalize_L2(query.reshape(1, -1))
    encoder = _FakeEncoder(query)
    monkeypatch.setattr(service_module, "TextEncoder", lambda *args, **kwargs: encoder)
    translator = _Translator("an english query")

    response = SearchService(cfg, translator=translator).search("a query", top_k=2)

    assert translator.inputs == ["a query"]
    assert encoder.inputs == ["an english query"]
    assert response.query == "a query"
    assert response.translated_query == "an english query"
    assert len(response.results) == 2
    assert {hit.shot_idx for hit in response.results} == {0, 1}
    assert response.results[0].video_id == "V1"
    assert response.results[0].keyframe_url.startswith("/api/keyframes/V1/g0/")

    by_shot = {hit.shot_idx: hit for hit in response.results}
    assert (by_shot[0].start_ms, by_shot[0].end_ms) == (0, 30_000)
    assert (by_shot[1].start_ms, by_shot[1].end_ms) == (30_000, 60_000)

    frames = by_shot[0].frames
    assert [frame.ts_ms for frame in frames] == [4500, 5000, 5500]
    keyframe = next(frame for frame in frames if frame.is_keyframe)
    assert keyframe.ts_ms == 5000
    assert keyframe.url.startswith("/api/keyframes/V1/g0/")
    assert (keyframe.start_ms, keyframe.end_ms) == (4500, 5500)
    follows = [frame for frame in frames if not frame.is_keyframe]
    assert [frame.ts_ms for frame in follows] == [4500, 5500]
    assert all(frame.url.startswith("/api/frames/V1/g0/") for frame in follows)
    assert len(by_shot[1].frames) == 1

    assert response.dres_payload is not None
    answer = response.dres_payload.answerSets[0].answers[0]
    assert answer.media_item_name == "V1"
    assert answer.start == keyframe.start_ms
    assert answer.end == keyframe.end_ms


def test_search_filters_by_object(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        corpus_dir=tmp_path / "corpus",
        artifacts_dir=tmp_path / "artifacts",
    )
    init_db(cfg.db_path)

    with closing(connect(cfg.db_path)) as conn:
        upsert_video(
            conn,
            Video(video_id="V1", path=str(tmp_path / "V1.mp4"), duration_ms=60_000),
        )
        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('V1', 0, 0, 0, 10000), ('V1', 0, 1, 10000, 20000), "
            "('V1', 0, 2, 20000, 30000)"
        )
        conn.commit()
        uids = [
            insert_keyframe(
                conn,
                Keyframe(
                    video_id="V1",
                    shot_idx=shot_idx,
                    kf_idx=0,
                    ts_ms=(shot_idx + 1) * 1000,
                    path=f"keyframes/V1/g0/{shot_idx:06d}_000.jpg",
                ),
            )
            for shot_idx in range(3)
        ]
        set_keyframe_objects(conn, uids[0], {"person": 1})
        set_keyframe_objects(conn, uids[1], {"person": 1, "car": 2})
        set_keyframe_objects(conn, uids[2], {"car": 1})
        conn.commit()

    vectors = np.zeros((3, cfg.embed.dim), dtype=np.float32)
    vectors[0, 0] = 1.0
    vectors[1, 0], vectors[1, 1] = 0.9, 0.1
    vectors[2, 0], vectors[2, 2] = 0.8, 0.1
    _write_embeddings(cfg.embeddings_dir, vectors, np.asarray(uids), cfg.embed.model)

    query = vectors[0].copy()
    faiss.normalize_L2(query.reshape(1, -1))
    encoder = _FakeEncoder(query)
    monkeypatch.setattr(service_module, "TextEncoder", lambda *args, **kwargs: encoder)
    service = SearchService(cfg, translator=_Translator())

    person = service.search("a person", top_k=10, objects=["PERSON"])
    car = service.search("a person", top_k=10, objects=["car"])
    both = service.search("a person", top_k=10, objects=["person", "car"])

    assert [hit.shot_idx for hit in person.results] == [0, 1]
    assert [hit.shot_idx for hit in car.results] == [1, 2]
    assert [hit.shot_idx for hit in both.results] == [1]
    assert person.results[1].evidence.objects == ["car", "person"]


def test_search_selects_model_and_lazy_loads(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        corpus_dir=tmp_path / "corpus",
        artifacts_dir=tmp_path / "artifacts",
        embed=EmbedConfig(
            default="clip",
            profiles=[
                EmbedProfile(name="clip", model="clip-model", dim=2, dir="embed"),
                EmbedProfile(
                    name="siglip2",
                    model="siglip-model",
                    dim=3,
                    dir="embed_siglip2",
                    encoder="open_clip",
                ),
            ],
        ),
    )
    init_db(cfg.db_path)

    with closing(connect(cfg.db_path)) as conn:
        upsert_video(
            conn,
            Video(video_id="V1", path=str(tmp_path / "V1.mp4"), duration_ms=60_000),
        )
        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('V1', 0, 0, 0, 10000), ('V1', 0, 1, 10000, 20000)"
        )
        conn.commit()
        uids = [
            insert_keyframe(
                conn,
                Keyframe(
                    video_id="V1",
                    shot_idx=shot_idx,
                    kf_idx=0,
                    ts_ms=(shot_idx + 1) * 1000,
                    path=f"keyframes/V1/g0/{shot_idx:06d}_000.jpg",
                ),
            )
            for shot_idx in range(2)
        ]

    _write_embeddings(
        cfg.embeddings_dir_for("clip"),
        np.array([[1.0, 0.0], [0.0, 1.0]]),
        np.asarray(uids),
        "clip-model",
    )
    _write_embeddings(
        cfg.embeddings_dir_for("siglip2"),
        np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        np.asarray(uids),
        "siglip-model",
    )

    calls: list[tuple[str, int, str]] = []

    def _encoder_factory(name, dim, backend="sentence_transformers", fp16=False):
        calls.append((name, dim, backend))
        vector = np.zeros(dim, dtype=np.float32)
        vector[0] = 1.0
        return _FakeEncoder(vector)

    monkeypatch.setattr(service_module, "TextEncoder", _encoder_factory)
    service = SearchService(cfg, translator=_Translator())

    models = service.models()
    assert [item["name"] for item in models] == ["clip", "siglip2"]
    assert models[0]["default"] is True
    assert all(item["available"] for item in models)
    assert [item["dim"] for item in models] == [2, 3]

    clip = service.search("q", top_k=2)
    assert clip.model == "clip"
    assert len(clip.results) == 2
    assert calls == [("clip-model", 2, "sentence_transformers")]

    siglip = service.search("q", top_k=2, model="siglip2")
    assert siglip.model == "siglip2"
    assert len(siglip.results) == 2
    assert calls[-1] == ("siglip-model", 3, "open_clip")

    service.search("q", top_k=2)
    assert len(calls) == 2

    with pytest.raises(ValueError):
        service.search("q", model="missing")


def test_search_rejects_empty_query(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(artifacts_dir=tmp_path / "artifacts")
    monkeypatch.setattr(
        service_module,
        "TextEncoder",
        lambda *args, **kwargs: _FakeEncoder(np.zeros(cfg.embed.dim, dtype=np.float32)),
    )

    with pytest.raises(ValueError):
        SearchService(cfg, translator=_Translator()).search("   ")
