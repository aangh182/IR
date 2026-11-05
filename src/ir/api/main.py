from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import AppConfig, load_config
from ..search.service import SearchService
from ..store.db import init_db
from .routes import router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db(app.state.config.db_path)
    app.state.search_service.warmup()
    yield


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    app = FastAPI(title="AIC2024 Known-Item Search", version=__version__, lifespan=_lifespan)
    app.state.config = cfg
    app.state.search_service = SearchService(cfg)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
