from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import AppConfig

__all__ = ["DresClient", "DresError", "EvaluationInfo", "TaskInfo", "dres_session"]


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
        self, method: str, path: str, *, body: dict[str, Any] | None = None
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
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = _error_detail(raw) or exc.reason
            raise DresError(f"DRES {exc.code}: {detail}", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise DresError(f"Không kết nối được DRES: {exc.reason}") from exc

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise DresError("DRES trả về dữ liệu không phải JSON") from exc

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
        video_id: str,
        start_ms: int,
        end_ms: int,
        *,
        evaluation_id: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        target = evaluation_id or self.evaluation_id or self.active_evaluation().id
        answer: dict[str, Any] = {
            "mediaItemName": video_id,
            "start": int(start_ms),
            "end": int(end_ms),
        }
        if collection:
            answer["mediaItemCollectionName"] = collection

        payload = self._request(
            "POST",
            f"/api/v2/submit/{target}",
            body={"answerSets": [{"answers": [answer]}]},
        )
        return payload or {}

    def describe_submission(
        self, video_id: str, start_ms: int, end_ms: int, *, collection: str | None = None
    ) -> dict[str, Any]:
        answer: dict[str, Any] = {
            "mediaItemName": video_id,
            "start": int(start_ms),
            "end": int(end_ms),
        }
        if collection:
            answer["mediaItemCollectionName"] = collection
        return {"answerSets": [{"answers": [answer]}]}


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
