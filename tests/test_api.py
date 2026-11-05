from __future__ import annotations

from contextlib import closing

from fastapi.testclient import TestClient

from ir.api.main import create_app
from ir.config import AppConfig
from ir.store.db import connect, init_db, upsert_video
from ir.types import Video


def test_health_and_stats(tmp_path) -> None:
    app = create_app(AppConfig(artifacts_dir=tmp_path / "artifacts"))

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["db_ready"] is True
        assert body["index_ready"] is False

        stats = client.get("/api/stats")
        assert stats.status_code == 200
        assert stats.json() == {
            "videos": 0,
            "shots": 0,
            "keyframes": 0,
            "follow_frames": 0,
            "asr_segments": 0,
        }


def test_search_without_index_returns_503(tmp_path) -> None:
    app = create_app(AppConfig(artifacts_dir=tmp_path / "artifacts"))

    with TestClient(app) as client:
        response = client.post("/api/search", json={"text": "a person"})

    assert response.status_code == 503
    assert "embedding" in response.json()["detail"].lower()


def test_stream_video_supports_range(tmp_path) -> None:
    cfg = AppConfig(
        corpus_dir=tmp_path / "corpus",
        artifacts_dir=tmp_path / "artifacts",
    )
    video_path = cfg.corpus_dir / "V1.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"0123456789")

    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        upsert_video(conn, Video(video_id="V1", path=str(video_path), duration_ms=1000))

    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.get("/api/videos/V1/stream", headers={"Range": "bytes=0-3"})

    assert response.status_code == 206
    assert response.content == b"0123"


def test_keyframe_route(tmp_path) -> None:
    cfg = AppConfig(artifacts_dir=tmp_path / "artifacts")
    keyframe_path = cfg.keyframes_dir / "V1" / "g0" / "000000_000.jpg"
    keyframe_path.parent.mkdir(parents=True)
    keyframe_path.write_bytes(b"jpeg-bytes")

    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.get("/api/keyframes/V1/g0/000000_000.jpg")

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"


def test_follow_frame_route(tmp_path) -> None:
    cfg = AppConfig(artifacts_dir=tmp_path / "artifacts")
    frame_path = cfg.follow_frames_dir / "V1" / "g0" / "000000_000_001.jpg"
    frame_path.parent.mkdir(parents=True)
    frame_path.write_bytes(b"follow-bytes")

    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.get("/api/frames/V1/g0/000000_000_001.jpg")
        missing = client.get("/api/frames/V1/g0/missing.jpg")

    assert response.status_code == 200
    assert response.content == b"follow-bytes"
    assert missing.status_code == 404

