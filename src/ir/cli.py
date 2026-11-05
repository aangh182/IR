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
    init_db(cfg.db_path)
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
        typer.Option("--only", help="Chỉ chạy bước shots, keyframes và/hoặc follow."),
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
        f"follow_frames={report.follow_frames} "
        f"skipped={report.skipped} failed={report.failed}"
    )
    for error in report.errors:
        typer.echo(f"  - {error}", err=True)
    if report.failed:
        raise typer.Exit(code=1)


@app.command()
def merge(
    shards: Annotated[
        Path | None, typer.Option(help="Thư mục shards; mặc định artifacts/.../shards.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option(help="Thư mục output; mặc định cạnh thư mục shards.")
    ] = None,
) -> None:
    from .index.merge import merge_shards

    cfg = load_config()
    try:
        report = merge_shards(cfg, shards, output)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"merged videos={report.videos} keyframes={report.keyframes} -> {report.output_dir}"
    )


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Mô tả sự kiện (tiếng Anh).")],
    top_k: Annotated[int, typer.Option("--top-k", "-k", min=1, max=50)] = 20,
    as_json: Annotated[bool, typer.Option("--json", help="In JSON.")] = False,
) -> None:
    from .search.service import IndexUnavailableError, SearchService

    cfg = load_config()
    init_db(cfg.db_path)
    try:
        response = SearchService(cfg).search(query, top_k)
    except (IndexUnavailableError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(response.model_dump_json(indent=2))
        return

    typer.echo(f"{len(response.results)} kết quả · {response.elapsed_ms} ms")
    for rank, hit in enumerate(response.results, start=1):
        typer.echo(
            f"{rank:>2}. {hit.video_id}  {_format_ms(hit.start_ms)} → {_format_ms(hit.end_ms)}  "
            f"score={hit.score:.4f}"
        )
        typer.echo(f"    {hit.keyframe_url}")


@app.command()
def serve(reload: bool = False) -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run("ir.api.main:app", host=cfg.api.host, port=cfg.api.port, reload=reload)


def _format_ms(value: int) -> str:
    seconds, milliseconds = divmod(max(0, value), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
