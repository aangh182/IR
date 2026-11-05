from __future__ import annotations

from contextlib import closing

from ir.config import AppConfig
from ir.index import build as build_module
from ir.store.db import connect, get_stats
from ir.types import Keyframe, Shot, Video


def test_build_resumes_and_reindexes(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(corpus_dir=tmp_path / "corpus", artifacts_dir=tmp_path / "artifacts")
    video = Video(
        video_id="L21_V001",
        path=str(tmp_path / "L21_V001.mp4"),
        duration_ms=2000,
        fps=25.0,
    )
    calls: list[str] = []

    monkeypatch.setattr(build_module, "scan_corpus", lambda _: [video])
    monkeypatch.setattr(
        build_module,
        "detect_shots",
        lambda *args, **kwargs: calls.append("shots")
        or [Shot(video_id="L21_V001", shot_idx=0, start_ms=0, end_ms=2000)],
    )
    monkeypatch.setattr(
        build_module,
        "extract_keyframes",
        lambda *args, **kwargs: calls.append("keyframes")
        or [
            Keyframe(
                video_id="L21_V001",
                shot_idx=0,
                kf_idx=0,
                ts_ms=1000,
                path="keyframes/L21_V001/g0/000000_000.jpg",
            )
        ],
    )

    first = build_module.build(cfg)
    assert (first.videos, first.shots, first.keyframes, first.failed) == (1, 1, 1, 0)

    second = build_module.build(cfg)
    assert second.skipped == 1
    assert (second.shots, second.keyframes) == (0, 0)

    third = build_module.build(cfg, reindex=True)
    assert (third.shots, third.keyframes, third.skipped) == (1, 1, 0)

    assert calls == ["shots", "keyframes", "shots", "keyframes"]

    with closing(connect(cfg.db_path)) as conn:
        assert get_stats(conn) == {
            "videos": 1,
            "shots": 1,
            "keyframes": 1,
            "asr_segments": 0,
        }
