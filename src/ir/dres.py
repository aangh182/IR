from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig

__all__ = [
    "DresClient",
    "DresError",
    "EvaluationInfo",
    "SubmitOutcome",
    "TaskInfo",
    "answer_kind_for_group",
    "dres_session",
    "kis_answer",
    "qa_answer",
    "raw_submission",
    "trake_answer",
]


def dres_session(cfg: AppConfig) -> str | None:
    return (
        os.environ.get("DRES_SESSION_ID")
        or cfg.dres.session_id
        or _session_from_file(cfg)
    )


class DresError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class TaskInfo:
    name: str
    task_group: str
    task_type: str
    duration: int | None = None

    @property
    def is_visual(self) -> bool:
        return self.task_group.lower() == "vkis"


@dataclass(frozen=True)
class EvaluationInfo:
    id: str
    name: str
    type: str
    status: str
    task_templates: list[TaskInfo]


@dataclass(frozen=True)
class SubmitOutcome:
    status: bool
    verdict: str
    description: str
    http_status: int

    @property
    def is_correct(self) -> bool:
        return self.verdict == "CORRECT"

    @property
    def is_wrong(self) -> bool:
        return self.verdict == "WRONG"

    @property
    def is_review(self) -> bool:
        return self.verdict in {"INDETERMINATE", "UNDECIDABLE"}


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts"}


def normalize_video_id(video_id: str) -> str:
    value = video_id.strip()
    suffix = Path(value).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return value[: -len(suffix)]
    return value


def kis_answer(video_id: str, ts_ms: int) -> dict[str, Any]:
    frame_ms = max(0, int(ts_ms))
    return {
        "mediaItemName": normalize_video_id(video_id),
        "start": frame_ms,
        "end": frame_ms,
    }


def qa_answer(answer: str, video_id: str, ts_ms: int) -> dict[str, Any]:
    text = f"QA-{answer.strip()}-{normalize_video_id(video_id)}-{max(0, int(ts_ms))}"
    return {"text": text}


def trake_answer(video_id: str, frame_ids: Sequence[int]) -> dict[str, Any]:
    if not frame_ids:
        raise DresError("TRAKE cần ít nhất một frame id")
    joined = ",".join(str(int(frame)) for frame in frame_ids)
    return {"text": f"TR-{normalize_video_id(video_id)}-{joined}"}


def raw_submission(body: dict[str, Any]) -> list[dict[str, Any]]:
    answer_sets = body.get("answerSets")
    if not isinstance(answer_sets, list) or not answer_sets:
        raise DresError("Payload phải có answerSets không rỗng")
    answers: list[dict[str, Any]] = []
    for answer_set in answer_sets:
        if not isinstance(answer_set, dict):
            raise DresError("Mỗi answerSet phải là object")
        items = answer_set.get("answers")
        if not isinstance(items, list):
            raise DresError("Mỗi answerSet phải có answers")
        answers.extend(item for item in items if isinstance(item, dict))
    if not answers:
        raise DresError("Payload không có answer nào")
    return answers


def answer_kind_for_group(task_group: str) -> str:
    group = task_group.strip().lower()
    if group == "qa":
        return "qa"
    if group == "trake":
        return "trake"
    return "kis"


class DresClient:
    def __init__(
        self,
        base_url: str,
        session_id: str,
        *,
        evaluation_id: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not session_id:
            raise DresError("Thiếu DRES session id")
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.evaluation_id = evaluation_id
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: AppConfig) -> DresClient:
        base_url = os.environ.get("DRES_BASE_URL") or cfg.dres.base_url
        evaluation = os.environ.get("DRES_EVALUATION_ID") or cfg.dres.evaluation_id
        return cls(
            base_url,
            dres_session(cfg) or "",
            evaluation_id=evaluation,
            timeout=cfg.dres.timeout_sec,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        with_status: bool = False,
    ) -> Any:
        query = urllib.parse.urlencode({"session": self.session_id})
        url = f"{self.base_url}{path}?{query}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status_code = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = _error_detail(raw) or exc.reason
            raise DresError(_describe_http_error(exc.code, detail), status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise DresError(f"Không kết nối được DRES: {exc.reason}") from exc

        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError as exc:
                raise DresError("DRES trả về dữ liệu không phải JSON") from exc

        if with_status:
            return status_code, payload
        return payload

    def list_evaluations(self) -> list[EvaluationInfo]:
        payload = self._request("GET", "/api/v2/client/evaluation/list") or []
        return [
            EvaluationInfo(
                id=str(item["id"]),
                name=str(item["name"]),
                type=str(item.get("type", "")),
                status=str(item.get("status", "")),
                task_templates=[
                    TaskInfo(
                        name=str(template["name"]),
                        task_group=str(template.get("taskGroup", "")),
                        task_type=str(template.get("taskType", "")),
                        duration=template.get("duration"),
                    )
                    for template in item.get("taskTemplates", [])
                ],
            )
            for item in payload
        ]

    def active_evaluation(self) -> EvaluationInfo:
        if self.evaluation_id:
            for evaluation in self.list_evaluations():
                if evaluation.id == self.evaluation_id:
                    return evaluation
            raise DresError(f"Không thấy evaluation {self.evaluation_id}")
        active = [item for item in self.list_evaluations() if item.status == "ACTIVE"]
        if not active:
            raise DresError("Không có evaluation nào đang ACTIVE")
        return active[0]

    def current_task(self, evaluation_id: str | None = None) -> TaskInfo | None:
        target = evaluation_id or self.evaluation_id
        if not target:
            target = self.active_evaluation().id
        payload = self._request(
            "GET", f"/api/v2/client/evaluation/currentTask/{target}"
        )
        if not payload:
            return None
        return TaskInfo(
            name=str(payload.get("name", "")),
            task_group=str(payload.get("taskGroup", "")),
            task_type=str(payload.get("taskType", "")),
            duration=payload.get("duration"),
        )

    def submit(
        self,
        answers: Sequence[dict[str, Any]],
        *,
        evaluation_id: str | None = None,
        task_id: str | None = None,
    ) -> SubmitOutcome:
        if not answers:
            raise DresError("Không có đáp án nào để nộp")
        target = evaluation_id or self.evaluation_id or self.active_evaluation().id
        answer_set: dict[str, Any] = {"answers": list(answers)}
        if task_id:
            answer_set["taskId"] = task_id

        status_code, payload = self._request(
            "POST",
            f"/api/v2/submit/{target}",
            body={"answerSets": [answer_set]},
            with_status=True,
        )
        body = payload if isinstance(payload, dict) else {}
        verdict = str(body.get("submission") or "")
        if status_code not in (200, 202) or not body.get("status", False):
            raise DresError(
                _describe_submit_failure(status_code, body, verdict),
                status=status_code,
            )
        return SubmitOutcome(
            status=True,
            verdict=verdict or "INDETERMINATE",
            description=str(body.get("description") or ""),
            http_status=status_code,
        )


_HTTP_HINTS = {
    401: "Session ID đã hết hạn — đăng nhập lại DRES và cập nhật session.",
    404: "Sai Evaluation ID hoặc task không tồn tại.",
    412: "Bài nộp bị từ chối: nộp trùng kết quả, hoặc thời gian làm bài đã hết.",
}


def _describe_http_error(status: int, detail: object) -> str:
    hint = _HTTP_HINTS.get(status)
    base = f"HTTP {status}: {detail}"
    return f"{base} — {hint}" if hint else base


def _describe_submit_failure(
    status: int, body: dict[str, Any], verdict: str
) -> str:
    detail = body.get("description") or verdict or "không rõ lý do"
    return _describe_http_error(status, detail)


def _session_from_file(cfg: AppConfig) -> str | None:
    path = cfg.state_root / "dres_session"
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _error_detail(raw: bytes) -> str | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        text = raw.decode("utf-8", errors="replace").strip()
        return text or None
    if isinstance(payload, dict):
        description = payload.get("description")
        if isinstance(description, str):
            return description
    return json.dumps(payload)[:300]
