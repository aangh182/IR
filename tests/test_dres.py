from __future__ import annotations

import json

import pytest

from ir.config import AppConfig, DresConfig
from ir.dres import (
    DresClient,
    DresError,
    kis_answer,
    normalize_video_id,
    qa_answer,
    raw_submission,
    trake_answer,
)


def _client(**kwargs) -> DresClient:
    return DresClient("https://example.test/dres/", "session-token", **kwargs)


def test_normalize_video_id_strips_known_extension() -> None:
    assert normalize_video_id(" video_0108.mp4 ") == "video_0108"
    assert normalize_video_id("video_0108.MKV") == "video_0108"
    assert normalize_video_id("video_0108") == "video_0108"


def test_kis_answer_collapses_start_and_end() -> None:
    assert kis_answer("video_0108.mp4", 18500) == {
        "mediaItemName": "video_0108",
        "start": 18500,
        "end": 18500,
    }


def test_qa_answer_uses_text_format() -> None:
    assert qa_answer("42", "video_0108", 24300) == {
        "text": "QA-42-video_0108-24300"
    }


def test_trake_answer_joins_frames() -> None:
    assert trake_answer("video_0055", [140, 395, 820, 1450]) == {
        "text": "TR-video_0055-140,395,820,1450"
    }


def test_trake_requires_a_frame() -> None:
    with pytest.raises(DresError):
        trake_answer("video_0055", [])


def test_raw_submission_extracts_answers() -> None:
    answers = raw_submission(
        {"answerSets": [{"answers": [{"text": "QA-1-v-1"}]}]}
    )
    assert answers == [{"text": "QA-1-v-1"}]


@pytest.mark.parametrize(
    "payload",
    [{}, {"answerSets": []}, {"answerSets": [{"answers": []}]}, {"answerSets": [{}]}],
)
def test_raw_submission_rejects_bad_payloads(payload) -> None:
    with pytest.raises(DresError):
        raw_submission(payload)


def test_request_sends_session_query_and_strips_trailing_slash(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["timeout"] = timeout

        class _Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"username": "team06_t5"}).encode()

        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert _client()._request("GET", "/api/v2/user") == {"username": "team06_t5"}
    assert seen["url"] == "https://example.test/dres/api/v2/user?session=session-token"
    assert seen["method"] == "GET"
    assert seen["timeout"] == 15.0


@pytest.mark.parametrize(
    "verdict,category,is_correct,is_wrong,is_review",
    [
        ("CORRECT", "correct", True, False, False),
        ("WRONG", "wrong", False, True, False),
        ("INDETERMINATE", "review", False, False, True),
        ("UNDECIDABLE", "review", False, False, True),
    ],
)
def test_submit_returns_outcome(
    monkeypatch, verdict, category, is_correct, is_wrong, is_review
) -> None:
    def fake_request(self, method, path, *, body=None, with_status=False):
        assert method == "POST"
        assert path == "/api/v2/submit/eval-1"
        assert body == {
            "answerSets": [
                {
                    "answers": [
                        {"mediaItemName": "L01_V001", "start": 1000, "end": 1000}
                    ]
                }
            ]
        }
        return 200, {"status": True, "description": "ok", "submission": verdict}

    monkeypatch.setattr(DresClient, "_request", fake_request)
    outcome = _client(evaluation_id="eval-1").submit([kis_answer("L01_V001", 1000)])

    assert outcome.verdict == verdict
    assert outcome.is_correct is is_correct
    assert outcome.is_wrong is is_wrong
    assert outcome.is_review is is_review
    assert outcome.http_status == 200


def test_submit_accepts_202_review(monkeypatch) -> None:
    monkeypatch.setattr(
        DresClient,
        "_request",
        lambda self, *a, **k: (202, {"status": True, "submission": "INDETERMINATE"}),
    )
    outcome = _client(evaluation_id="eval-1").submit([kis_answer("v", 10)])
    assert outcome.http_status == 202
    assert outcome.is_review is True


@pytest.mark.parametrize("status", [401, 404, 412])
def test_submit_failure_has_hint(monkeypatch, status) -> None:
    monkeypatch.setattr(
        DresClient,
        "_request",
        lambda self, *a, **k: (status, {"status": False, "description": "nope"}),
    )
    with pytest.raises(DresError) as excinfo:
        _client(evaluation_id="eval-1").submit([kis_answer("v", 10)])

    assert excinfo.value.status == status
    assert str(status) in str(excinfo.value)


def test_active_evaluation_prefers_explicit_id(monkeypatch) -> None:
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
