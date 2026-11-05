from __future__ import annotations

import json
from contextlib import closing

import faiss
import numpy as np
import pytest

import ir.search.service as service_module
from ir.config import AppConfig
from ir.search.service import SearchService
from ir.store.db import connect, init_db, insert_follow_frame, insert_keyframe, upsert_video
from ir.types import FollowFrame, Keyframe, Video


class _FakeEncoder:
    def __init__(self, vector: np.ndarray) -> None:
        self.vector = vector

    def encode(self, text: str) -> np.ndarray:
        return self.vector


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

        for frame_idx, ts_ms in enumerate((5500, 6000)):
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
    monkeypatch.setattr(
        service_module, "TextEncoder", lambda *args, **kwargs: _FakeEncoder(query)
    )

    response = SearchService(cfg).search("a query", top_k=2)

    assert len(response.results) == 2
    assert {hit.shot_idx for hit in response.results} == {0, 1}
    assert response.results[0].video_id == "V1"
    assert response.results[0].keyframe_url.startswith("/api/keyframes/V1/g0/")

    by_shot = {hit.shot_idx: hit for hit in response.results}
    assert (by_shot[0].start_ms, by_shot[0].end_ms) == (0, 30_000)
    assert (by_shot[1].start_ms, by_shot[1].end_ms) == (30_000, 60_000)

    frames = by_shot[0].frames
    assert len(frames) == 3
    assert frames[0].is_keyframe is True
    assert frames[0].ts_ms == 5000
    assert frames[0].url.startswith("/api/keyframes/V1/g0/")
    assert (frames[0].start_ms, frames[0].end_ms) == (4500, 5500)
    assert [frame.ts_ms for frame in frames[1:]] == [5500, 6000]
    assert frames[1].url.startswith("/api/frames/V1/g0/")
    assert len(by_shot[1].frames) == 1

    assert response.dres_payload is not None
    answer = response.dres_payload.answerSets[0].answers[0]
    assert answer.media_item_name == "V1"
    assert answer.start == frames[0].start_ms
    assert answer.end == frames[0].end_ms


def test_search_rejects_empty_query(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(artifacts_dir=tmp_path / "artifacts")
    monkeypatch.setattr(
        service_module,
        "TextEncoder",
        lambda *args, **kwargs: _FakeEncoder(np.zeros(cfg.embed.dim, dtype=np.float32)),
    )

    with pytest.raises(ValueError):
        SearchService(cfg).search("   ")
