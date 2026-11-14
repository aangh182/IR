from __future__ import annotations

import mimetypes
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..config import AppConfig
from ..dres import (
    DresClient,
    DresError,
    dres_session,
    kis_answer,
    qa_answer,
    raw_submission,
    trake_answer,
)
from ..search.service import IndexUnavailableError, SearchService
from ..store.db import connect, get_stats, object_facets
from ..types import SearchResponse

router = APIRouter(prefix="/api", tags=["search"])

mimetypes.add_type("image/webp", ".webp")


class SearchRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    objects: list[str] = Field(default_factory=list, max_length=20)
    model: str | None = None
    include_boilerplate: bool = False
    dedup: bool = True


class SimilarRequest(BaseModel):
    kf_uid: int = Field(ge=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    objects: list[str] = Field(default_factory=list, max_length=20)
    model: str | None = None
    include_boilerplate: bool = False
    dedup: bool = True


class TimelineRequest(BaseModel):
    kf_uid: int = Field(ge=1)
    before: int | None = Field(default=None, ge=0, le=100)
    after: int | None = Field(default=None, ge=0, le=100)


class DresSubmitRequest(BaseModel):
    kind: Literal["kis", "vkis", "qa", "trake", "raw"] = "kis"
    video_id: str | None = None
    ts_ms: int | None = Field(default=None, ge=0)
    answer: str | None = None
    frame_ids: list[int] | None = None
    payload: dict[str, Any] | None = None
    task_id: str | None = None


def _config(request: Request) -> AppConfig:
    return request.app.state.config


def _service(request: Request) -> SearchService:
    return request.app.state.search_service


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    cfg = _config(request)
    models = _service(request).models()
    default = next((item for item in models if item["default"]), None)

    return {
        "status": "ok",
        "version": __version__,
        "db": str(cfg.db_path),
        "db_ready": cfg.db_path.exists(),
        "index_ready": any(bool(item["available"]) for item in models),
        "index_count": default["keyframes"] if default else None,
        "index_model": default["model"] if default else None,
    }


@router.get("/stats")
def stats(request: Request) -> dict[str, int]:
    cfg = _config(request)
    with closing(connect(cfg.db_path)) as conn:
        return get_stats(conn)


@router.get("/models")
def models(request: Request) -> list[dict[str, object]]:
    return _service(request).models()


@router.get("/objects")
def objects(request: Request, limit: int = 200) -> list[dict[str, object]]:
    cfg = _config(request)
    with closing(connect(cfg.db_path)) as conn:
        return object_facets(conn, max(1, min(limit, 500)))


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, request: Request) -> SearchResponse:
    try:
        return _service(request).search(
            payload.text,
            payload.top_k,
            objects=payload.objects,
            model=payload.model,
            include_boilerplate=payload.include_boilerplate,
            dedup=payload.dedup,
        )
    except IndexUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/similar", response_model=SearchResponse)
def similar(payload: SimilarRequest, request: Request) -> SearchResponse:
    try:
        return _service(request).search_similar(
            payload.kf_uid,
            payload.top_k,
            objects=payload.objects,
            model=payload.model,
            include_boilerplate=payload.include_boilerplate,
            dedup=payload.dedup,
        )
    except IndexUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/timeline", response_model=SearchResponse)
def timeline(payload: TimelineRequest, request: Request) -> SearchResponse:
    try:
        return _service(request).timeline(
            payload.kf_uid,
            before=payload.before,
            after=payload.after,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dres/status")
def dres_status(request: Request) -> dict[str, object]:
    cfg = _config(request)
    if not dres_session(cfg):
        return {"configured": False, "user": None, "evaluation": None, "task": None}

    try:
        client = DresClient.from_config(cfg)
        user = client._request("GET", "/api/v2/user") or {}
        evaluation = client.active_evaluation()
        task = client.current_task(evaluation.id)
    except DresError as exc:
        return {
            "configured": True,
            "user": None,
            "evaluation": None,
            "task": None,
            "error": str(exc),
        }

    return {
        "configured": True,
        "base_url": client.base_url,
        "user": {"id": user.get("id"), "username": user.get("username"), "role": user.get("role")},
        "evaluation": {
            "id": evaluation.id,
            "name": evaluation.name,
            "status": evaluation.status,
            "type": evaluation.type,
        },
        "task": None
        if task is None
        else {
            "name": task.name,
            "task_group": task.task_group,
            "task_type": task.task_type,
            "duration": task.duration,
            "is_visual": task.is_visual,
        },
    }


@router.post("/dres/submit")
def dres_submit(payload: DresSubmitRequest, request: Request) -> dict[str, object]:
    cfg = _config(request)
    if not dres_session(cfg):
        raise HTTPException(status_code=400, detail="Chưa cấu hình DRES session id")

    try:
        answers = _dres_answers(payload)
    except DresError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client = DresClient.from_config(cfg)
    try:
        outcome = client.submit(answers, task_id=payload.task_id)
    except DresError as exc:
        status = 401 if exc.status == 401 else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return {
        "status": outcome.status,
        "submission": outcome.verdict,
        "description": outcome.description,
        "http_status": outcome.http_status,
        "category": _verdict_category(outcome.verdict),
        "answers": answers,
    }


def _dres_answers(payload: DresSubmitRequest) -> list[dict[str, Any]]:
    if payload.kind == "raw":
        if payload.payload is None:
            raise DresError("Kind raw cần payload ApiClientSubmission")
        return raw_submission(payload.payload)

    if payload.kind == "trake":
        if not payload.video_id:
            raise DresError("Thiếu video_id")
        if not payload.frame_ids:
            raise DresError("TRAKE cần danh sách frame ids")
        return [trake_answer(payload.video_id, payload.frame_ids)]

    if not payload.video_id:
        raise DresError("Thiếu video_id")
    if payload.ts_ms is None:
        raise DresError("Thiếu ts_ms")

    if payload.kind == "qa":
        if not payload.answer:
            raise DresError("QA cần answer")
        return [qa_answer(payload.answer, payload.video_id, payload.ts_ms)]

    return [kis_answer(payload.video_id, payload.ts_ms)]


def _verdict_category(verdict: str) -> str:
    if verdict == "CORRECT":
        return "correct"
    if verdict == "WRONG":
        return "wrong"
    if verdict in {"INDETERMINATE", "UNDECIDABLE"}:
        return "review"
    return "unknown"


@router.get("/keyframes/{path:path}")
def keyframe(path: str, request: Request) -> FileResponse:
    cfg = _config(request)
    root = cfg.keyframes_dir.resolve()
    target = (root / path).resolve()

    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="keyframe not found")

    media_type = mimetypes.guess_type(target.name)[0] or "image/jpeg"
    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/frames/{path:path}")
def follow_frame(path: str, request: Request) -> FileResponse:
    cfg = _config(request)
    root = cfg.follow_frames_dir.resolve()
    target = (root / path).resolve()

    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="frame not found")

    media_type = mimetypes.guess_type(target.name)[0] or "image/jpeg"
    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/videos/{video_id}/stream")
def stream_video(video_id: str, request: Request) -> FileResponse:
    cfg = _config(request)
    with closing(connect(cfg.db_path)) as conn:
        row = conn.execute(
            "SELECT path FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="video not found")

    path = Path(str(row["path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="video file not found")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
