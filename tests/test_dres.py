from __future__ import annotations

import json

import pytest

from ir.config import AppConfig, DresConfig
from ir.dres import DresClient, DresError


def _client(**kwargs) -> DresClient:
    return DresClient("https://example.test/dres/", "session-token", **kwargs)


def test_strips_trailing_slash_and_uses_session_query(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["timeout"] = timeout

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"username": "team06_t5"}).encode()

        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = _client()

    assert client._request("GET", "/api/v2/user") == {"username": "team06_t5"}
    assert seen["url"] == "https://example.test/dres/api/v2/user?session=session-token"
    assert seen["method"] == "GET"
    assert seen["timeout"] == 15.0


def test_active_evaluation_prefers_reportee_id(monkeypatch) -> None:
    payload = [
        {"id": "e1", "name": "first", "type": "SYNCHRONOUS", "status": "TERMINATED"},
        {"id": "e2", "name": "second", "type": "SYNCHRONOUS", "status": "ACTIVE"},
    ]
    monkeypatch.setattr(DresClient, "_request", lambda self, *a, **k: payload)

    assert _client().active_evaluation().id == "e2"
    assert _client(evaluation_id="e1").active_evaluation().name == "first"


def test_active_evaluation_raises_without_active_run(monkeypatch) -> None:
    payload = [{"id": "e1", "name": "x", "type": "SYNCHRONOUS", "status": "TERMINATED"}]
    monkeypatch.setattr(DresClient, "_request", lambda self, *a, **k: payload)

    with pytest.raises(DresError):
        _client().active_evaluation()


def test_submit_posts_kis_answer_set(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, body=None):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {"status": True, "description": "ok", "submission": "CORRECT"}

    monkeypatch.setattr(DresClient, "_request", fake_request)
    result = _client(evaluation_id="eval-1").submit("L01_V001", 1000, 4000)

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/submit/eval-1"
    assert captured["body"] == {
        "answerSets": [
            {
                "answers": [
                    {"mediaItemName": "L01_V001", "start": 1000, "end": 4000}
                ]
            }
        ]
    }
    assert result["submission"] == "CORRECT"


def test_current_task_flags_visual_group(monkeypatch) -> None:
    payload = {
        "name": "vkis-1",
        "taskGroup": "vkis",
        "taskType": "Visual Known Item Search",
        "duration": 300,
    }
    monkeypatch.setattr(DresClient, "_request", lambda self, *a, **k: payload)

    task = _client(evaluation_id="eval-1").current_task()
    assert task is not None
    assert task.is_visual is True
    assert task.duration == 300


def test_session_resolution_order(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        dres=DresConfig(session_id="from-config"),
    )
    monkeypatch.delenv("DRES_SESSION_ID", raising=False)
    assert DresClient.from_config(cfg).session_id == "from-config"

    monkeypatch.setenv("DRES_SESSION_ID", "from-env")
    assert DresClient.from_config(cfg).session_id == "from-env"

    monkeypatch.delenv("DRES_SESSION_ID")
    cfg_file = AppConfig(artifacts_dir=tmp_path / "artifacts")
    session_path = cfg_file.state_root / "dres_session"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("from-file\n", encoding="utf-8")
    assert DresClient.from_config(cfg_file).session_id == "from-file"
