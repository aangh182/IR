from __future__ import annotations

from fastapi.testclient import TestClient

from ir.api.main import create_app
from ir.config import AppConfig


def test_health_and_stats(tmp_path) -> None:
    app = create_app(AppConfig(artifacts_dir=tmp_path / "artifacts"))

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["db_ready"] is True

        stats = client.get("/api/stats")
        assert stats.status_code == 200
        assert stats.json() == {"videos": 0, "shots": 0, "keyframes": 0, "asr_segments": 0}
