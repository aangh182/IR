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
    "EvaluationSelection",
    "SubmitOutcome",
    "TaskInfo",
    "TaskQuery",
    "answer_kind_for_group",
    "dres_evaluation_id",
    "dres_session",
    "kis_answer",
    "qa_answer",
    "raw_submission",
    "save_evaluation_id",
    "trake_answer",
]


def dres_session(cfg: AppConfig) -> str | None:
    return (
        os.environ.get("DRES_SESSION_ID")
        or cfg.dres.session_id
        or _session_from_file(cfg)
    )


def dres_evaluation_id(cfg: AppConfig) -> str | None:
    return (
        os.environ.get("DRES_EVALUATION_ID")
        or cfg.dres.evaluation_id
        or _evaluation_from_file(cfg)
    )


def save_evaluation_id(cfg: AppConfig, evaluation_id: str | None) -> None:
    path = cfg.state_root / "dres_evaluation"
    value = (evaluation_id or "").strip()
    if not value:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


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

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"


@dataclass(frozen=True)
class EvaluationSelection:
    selected: EvaluationInfo | None
    active: list[EvaluationInfo]
    explicit: bool

    @property
    def needs_choice(self) -> bool:
        return self.selected is None and len(self.active) > 1


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


@dataclass(frozen=True)
class TaskQuery:
    evaluation_id: str
    task_id: str | None
    task_template_id: str | None
    task_name: str
    task_group: str
    task_type: str
    task_status: str
    time_left: int | None
    query: str
    segments: list[str]
    has_image: bool


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
        return cls(
            base_url,
            dres_session(cfg) or "",
            evaluation_id=dres_evaluation_id(cfg),
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

    def resolve_evaluation(self) -> EvaluationSelection:
        evaluations = self.list_evaluations()
        active = [item for item in evaluations if item.is_active]

        if self.evaluation_id:
            for evaluation in evaluations:
                if evaluation.id != self.evaluation_id:
                    continue
                if any(item.id == evaluation.id for item in active):
                    choices = active
                else:
                    choices = [*active, evaluation]
                return EvaluationSelection(evaluation, choices, True)
            known = ", ".join(
                f"{item.name} ({item.id})" for item in active
            ) or "(không có đề ACTIVE)"
            raise DresError(
                f"Không thấy evaluation {self.evaluation_id}. Đề đang ACTIVE: {known}",
            )

        if len(active) == 1:
            return EvaluationSelection(active[0], active, False)
        return EvaluationSelection(None, active, False)

    def active_evaluation(self) -> EvaluationInfo:
        selection = self.resolve_evaluation()
        if selection.selected is not None:
            return selection.selected
        if selection.needs_choice:
            names = ", ".join(f"{item.name} ({item.id})" for item in selection.active)
            raise DresError(
                f"Có {len(selection.active)} evaluation đang ACTIVE: {names}. "
                "Chọn một evaluation trước khi nộp bài.",
            )
        raise DresError("Không có evaluation nào đang ACTIVE")

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

    def current_query(self, evaluation_id: str | None = None) -> TaskQuery:
        target = evaluation_id or self.evaluation_id
        if not target:
            target = self.active_evaluation().id

        task = self.current_task(target)
        state = self._request("GET", f"/api/v2/evaluation/{target}/state") or {}
        if not isinstance(state, dict):
            state = {}
        template_id = state.get("taskTemplateId")
        time_left = state.get("timeLeft")
        if not isinstance(time_left, (int, float)):
            time_left = None

        if not template_id:
            return TaskQuery(
                evaluation_id=target,
                task_id=str(state["taskId"]) if state.get("taskId") else None,
                task_template_id=None,
                task_name=task.name if task else "",
                task_group=task.task_group if task else "",
                task_type=task.task_type if task else "",
                task_status=str(state.get("taskStatus") or ""),
                time_left=time_left,
                query="",
                segments=[],
                has_image=False,
            )

        hint = self._request(
            "GET",
            f"/api/v2/evaluation/{target}/template/task/{template_id}/hint",
        ) or {}
        if not isinstance(hint, dict):
            hint = {}

        segments: list[str] = []
        has_image = False
        for item in hint.get("sequence") or []:
            if not isinstance(item, dict):
                continue
            content_type = str(item.get("contentType") or "").upper()
            content = item.get("content")
            if content_type == "TEXT" and isinstance(content, str) and content.strip():
                segments.append(content.strip())
            elif content_type in {"IMAGE", "VIDEO"}:
                has_image = True

        return TaskQuery(
            evaluation_id=target,
            task_id=str(state["taskId"]) if state.get("taskId") else None,
            task_template_id=str(template_id),
            task_name=task.name if task else "",
            task_group=task.task_group if task else "",
            task_type=task.task_type if task else "",
            task_status=str(state.get("taskStatus") or ""),
            time_left=time_left,
            query=" ".join(segments),
            segments=segments,
            has_image=has_image,
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


def _evaluation_from_file(cfg: AppConfig) -> str | None:
    path = cfg.state_root / "dres_evaluation"
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
