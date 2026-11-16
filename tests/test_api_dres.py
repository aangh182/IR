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


def _stub_status(monkeypatch, *, task_group: str = "tkis", evaluations=None) -> None:
    evaluations = evaluations or [
        {
            "id": "eval-1",
            "name": "Đề thi thử",
            "type": "SYNCHRONOUS",
            "status": "ACTIVE",
            "taskTemplates": [],
        }
    ]

    def fake_request(self, method, path, *, body=None, with_status=False):
        if path == "/api/v2/user":
            return {"id": "u1", "username": "team06_t5", "role": "PARTICIPANT"}
        if path == "/api/v2/client/evaluation/list":
            return evaluations
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


def test_dres_status_lists_both_active_evaluations(client, monkeypatch) -> None:
    _stub_status(
        monkeypatch,
        evaluations=[
            {
                "id": "eval-mock",
                "name": "Đề thi thử",
                "type": "SYNCHRONOUS",
                "status": "ACTIVE",
                "taskTemplates": [],
            },
            {
                "id": "eval-real",
                "name": "Đề thi",
                "type": "SYNCHRONOUS",
                "status": "ACTIVE",
                "taskTemplates": [],
            },
        ],
    )

    body = client.get("/api/dres/status").json()

    assert body["needs_choice"] is True
    assert body["evaluation"] is None
    assert body["task"] is None
    assert [item["name"] for item in body["evaluations"]] == ["Đề thi thử", "Đề thi"]


def test_submit_blocked_until_evaluation_chosen(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        dres=DresConfig(session_id="test-session"),
    )
    monkeypatch.delenv("DRES_SESSION_ID", raising=False)
    monkeypatch.delenv("DRES_EVALUATION_ID", raising=False)

    with TestClient(create_app(cfg)) as client:
        _stub_status(
            monkeypatch,
            evaluations=[
                {"id": "eval-mock", "name": "Đề thi thử", "status": "ACTIVE", "taskTemplates": []},
                {"id": "eval-real", "name": "Đề thi", "status": "ACTIVE", "taskTemplates": []},
            ],
        )

        response = client.post(
            "/api/dres/submit", json={"kind": "kis", "video_id": "v", "ts_ms": 10}
        )
        assert response.status_code == 502
        assert "ACTIVE" in response.json()["detail"]

        chosen = client.post("/api/dres/evaluation", json={"evaluation_id": "eval-real"})
        assert chosen.status_code == 200

        captured: dict[str, object] = {}

        def fake_submit(self, answers, *, evaluation_id=None, task_id=None):
            captured["evaluation_id"] = evaluation_id
            return SubmitOutcome(True, "CORRECT", "ok", 200)

        monkeypatch.setattr(DresClient, "submit", fake_submit)

        response = client.post(
            "/api/dres/submit", json={"kind": "kis", "video_id": "v", "ts_ms": 10}
        )
        assert response.status_code == 200
        assert captured["evaluation_id"] is None
        assert (cfg.state_root / "dres_evaluation").read_text(encoding="utf-8") == "eval-real"


def test_choose_unknown_evaluation_returns_404(client, monkeypatch) -> None:
    _stub_status(monkeypatch)

    response = client.post("/api/dres/evaluation", json={"evaluation_id": "nope"})
    assert response.status_code == 404


def test_submit_uses_request_evaluation_override(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_submit(self, answers, *, evaluation_id=None, task_id=None):
        captured["evaluation_id"] = evaluation_id
        return SubmitOutcome(True, "CORRECT", "ok", 200)

    monkeypatch.setattr(DresClient, "submit", fake_submit)

    body = client.post(
        "/api/dres/submit",
        json={"kind": "kis", "video_id": "v", "ts_ms": 10, "evaluation_id": "eval-x"},
    ).json()

    assert body["category"] == "correct"
    assert captured["evaluation_id"] == "eval-x"


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
