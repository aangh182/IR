from __future__ import annotations

import logging
import sys
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer

from .config import load_config
from .index.build import build
from .store.db import connect, get_stats, init_db

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="AIC2024 Known-Item Search pipeline",
)


@app.command()
def init() -> None:
    cfg = load_config()
    cfg.keyframes_dir.mkdir(parents=True, exist_ok=True)
    db_path = init_db(cfg.db_path)
    typer.echo(f"database: {db_path}")
    typer.echo(f"artifacts: {cfg.artifacts_dir}")


@app.command()
def stats() -> None:
    cfg = load_config()
    with closing(connect(cfg.db_path)) as conn:
        counts = get_stats(conn)
    for key, value in counts.items():
        typer.echo(f"{key:>14}: {value}")


@app.command()
def index(
    corpus: Annotated[Path | None, typer.Option(help="Thư mục corpus, mặc định config.")] = None,
    limit: Annotated[int | None, typer.Option(help="Chỉ index N video đầu tiên.")] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Chỉ chạy bước shots và/hoặc keyframes."),
    ] = None,
    reindex: Annotated[
        bool, typer.Option("--reindex", help="Index lại, tạo generation mới.")
    ] = False,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    report = build(cfg, corpus_dir=corpus, limit=limit, steps=only, reindex=reindex)
    typer.echo(
        f"videos={report.videos} shots={report.shots} keyframes={report.keyframes} "
        f"skipped={report.skipped} failed={report.failed}"
    )
    for error in report.errors:
        typer.echo(f"  - {error}", err=True)
    if report.failed:
        raise typer.Exit(code=1)


@app.command()
def search(query: str) -> None:
    typer.echo(f"Phase 2 chưa triển khai: CLIP + FAISS search cho {query!r}")
    raise typer.Exit(code=1)


@app.command()
def serve(reload: bool = False) -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run("ir.api.main:app", host=cfg.api.host, port=cfg.api.port, reload=reload)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
