from __future__ import annotations

import json
import mimetypes
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..config import AppConfig
from ..search.service import IndexUnavailableError, SearchService
from ..store.db import connect, get_stats
from ..types import SearchResponse

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)


def _config(request: Request) -> AppConfig:
    return request.app.state.config


def _service(request: Request) -> SearchService:
    return request.app.state.search_service


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    cfg = _config(request)
    index_ready = cfg.faiss_path.is_file() and cfg.id_map_path.is_file()

    index_model = None
    index_count = None
    if cfg.manifest_path.is_file():
        try:
            manifest = json.loads(cfg.manifest_path.read_text(encoding="utf-8"))
            index_model = manifest.get("model")
            index_count = manifest.get("count")
        except (OSError, ValueError):
            pass

    return {
        "status": "ok",
        "version": __version__,
        "db": str(cfg.db_path),
        "db_ready": cfg.db_path.exists(),
        "index_ready": index_ready,
        "index_count": index_count,
        "index_model": index_model,
    }


@router.get("/stats")
def stats(request: Request) -> dict[str, int]:
    cfg = _config(request)
    with closing(connect(cfg.db_path)) as conn:
        return get_stats(conn)


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, request: Request) -> SearchResponse:
    try:
        return _service(request).search(payload.text, payload.top_k)
    except IndexUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
