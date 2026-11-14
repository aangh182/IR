from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ir.api.main import create_app
from ir.config import AppConfig, DresConfig
from ir.dres import DresClient, DresError, SubmitOutcome


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    cfg = AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        dres=DresConfig(session_id="test-session"),
    )
    monkeypatch.delenv("DRES_SESSION_ID", raising=False)
    return TestClient(create_app(cfg))


def _stub_status(monkeypatch, *, task_group: str = "tkis") -> None:
    def fake_request(self, method, path, *, body=None, with_status=False):
        if path == "/api/v2/user":
            return {"id": "u1", "username": "team06_t5", "role": "PARTICIPANT"}
        if path == "/api/v2/client/evaluation/list":
            return [
                {
                    "id": "eval-1",
                    "name": "Đề thi thử",
                    "type": "SYNCHRONOUS",
                    "status": "ACTIVE",
                    "taskTemplates": [],
                }
            ]
        if path.startswith("/api/v2/client/evaluation/currentTask/"):
            return {
                "name": f"{task_group}-1",
                "taskGroup": task_group,
                "taskType": "Textual Known Item Search",
                "duration": 300,
            }
        raise AssertionError(path)

    monkeypatch.setattr(DresClient, "_request", fake_request)


def test_dres_status_without_session(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DRES_SESSION_ID", raising=False)
    app = create_app(AppConfig(artifacts_dir=tmp_path / "artifacts"))

    with TestClient(app) as client:
        body = client.get("/api/dres/status").json()

    assert body["configured"] is False
    assert body["user"] is None


def test_dres_status_reports_task(client, monkeypatch) -> None:
    _stub_status(monkeypatch)

    body = client.get("/api/dres/status").json()

    assert body["configured"] is True
    assert body["user"]["username"] == "team06_t5"
    assert body["evaluation"]["id"] == "eval-1"
    assert body["task"]["name"] == "tkis-1"
    assert body["task"]["is_visual"] is False


def test_dres_status_surfaces_dres_error(client, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise DresError("HTTP 401: hết hạn", status=401)

    monkeypatch.setattr(DresClient, "_request", boom)

    body = client.get("/api/dres/status").json()
    assert body["configured"] is True
    assert "401" in body["error"]


def test_submit_kis_builds_point_answer(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_submit(self, answers, *, evaluation_id=None, task_id=None):
        captured["answers"] = answers
        return SubmitOutcome(True, "CORRECT", "found it", 200)

    monkeypatch.setattr(DresClient, "submit", fake_submit)

    response = client.post(
        "/api/dres/submit",
        json={"kind": "kis", "video_id": "video_0108.mp4", "ts_ms": 18500},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "correct"
    assert captured["answers"] == [
        {"mediaItemName": "video_0108", "start": 18500, "end": 18500}
    ]


def test_submit_qa_uses_text_answer(client, monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        DresClient,
        "submit",
        lambda self, answers, **k: captured.update(answers=answers)
        or SubmitOutcome(True, "WRONG", "nope", 200),
    )

    body = client.post(
        "/api/dres/submit",
        json={"kind": "qa", "video_id": "video_0108", "ts_ms": 24300, "answer": "42"},
    ).json()

    assert body["category"] == "wrong"
    assert captured["answers"] == [{"text": "QA-42-video_0108-24300"}]


def test_submit_trake_joins_frames(client, monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        DresClient,
        "submit",
        lambda self, answers, **k: captured.update(answers=answers)
        or SubmitOutcome(True, "INDETERMINATE", "review", 202),
    )

    body = client.post(
        "/api/dres/submit",
        json={
            "kind": "trake",
            "video_id": "video_0055",
            "frame_ids": [140, 395, 820, 1450],
        },
    ).json()

    assert body["category"] == "review"
    assert captured["answers"] == [{"text": "TR-video_0055-140,395,820,1450"}]


def test_submit_rejects_missing_fields(client) -> None:
    response = client.post("/api/dres/submit", json={"kind": "kis", "video_id": "v"})
    assert response.status_code == 400


def test_submit_maps_unauthorized(client, monkeypatch) -> None:
    def boom(self, answers, **kwargs):
        raise DresError("HTTP 401: hết hạn", status=401)

    monkeypatch.setattr(DresClient, "submit", boom)

    response = client.post(
        "/api/dres/submit", json={"kind": "kis", "video_id": "v", "ts_ms": 10}
    )
    assert response.status_code == 401
