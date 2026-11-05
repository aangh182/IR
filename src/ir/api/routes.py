from __future__ import annotations

from contextlib import closing

from fastapi import APIRouter, Request

from .. import __version__
from ..config import AppConfig
from ..store.db import connect, get_stats

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    cfg: AppConfig = request.app.state.config
    return {
        "status": "ok",
        "version": __version__,
        "db": str(cfg.db_path),
        "db_ready": cfg.db_path.exists(),
    }


@router.get("/stats")
def stats(request: Request) -> dict[str, int]:
    cfg: AppConfig = request.app.state.config
    with closing(connect(cfg.db_path)) as conn:
        return get_stats(conn)
