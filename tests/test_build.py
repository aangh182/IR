from __future__ import annotations

from contextlib import closing

from ir.config import AppConfig
from ir.index import build as build_module
from ir.store.db import (
    connect,
    current_generation,
    get_index_status,
    get_stats,
)
from ir.types import FollowFrame, Keyframe, Shot, Video


def _patch_pipeline(tmp_path, monkeypatch, calls: list[str]) -> AppConfig:
    cfg = AppConfig(corpus_dir=tmp_path / "corpus", artifacts_dir=tmp_path / "artifacts")
    video = Video(
        video_id="L21_V001",
        path=str(tmp_path / "L21_V001.mp4"),
        duration_ms=2000,
        fps=25.0,
    )

    monkeypatch.setattr(build_module, "scan_corpus", lambda _: [video])
    monkeypatch.setattr(
        build_module,
        "detect_shots",
        lambda *args, **kwargs: (
            calls.append("shots")
            or [Shot(video_id="L21_V001", shot_idx=0, start_ms=0, end_ms=2000)]
        ),
    )
    monkeypatch.setattr(
        build_module,
        "extract_keyframes",
        lambda *args, **kwargs: (
            calls.append("keyframes")
            or [
                Keyframe(
                    video_id="L21_V001",
                    shot_idx=0,
                    kf_idx=0,
                    ts_ms=1000,
                    path="keyframes/L21_V001/g0/000000_000.jpg",
                )
            ]
        ),
    )

    def fake_follow(*args, **kwargs):
        calls.append("follow")
        return [
            FollowFrame(
                video_id="L21_V001",
                shot_idx=0,
                kf_idx=0,
                frame_idx=0,
                ts_ms=1500,
                path=f"follow_frames/L21_V001/g{args[6]}/000000_000_000.webp",
                generation=args[6],
            )
        ]

    monkeypatch.setattr(build_module, "extract_follow_frames", fake_follow)
    return cfg


def test_build_resumes_and_reindexes(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    cfg = _patch_pipeline(tmp_path, monkeypatch, calls)

    first = build_module.build(cfg)
    assert (first.videos, first.shots, first.keyframes, first.failed) == (1, 1, 1, 0)
    assert first.follow_frames == 1

    second = build_module.build(cfg)
    assert second.skipped == 1
    assert (second.shots, second.keyframes, second.follow_frames) == (0, 0, 0)

    third = build_module.build(cfg, reindex=True)
    assert (third.shots, third.keyframes, third.skipped) == (1, 1, 0)
    assert third.follow_frames == 1

    assert calls == ["shots", "keyframes", "follow", "shots", "keyframes", "follow"]

    with closing(connect(cfg.db_path)) as conn:
        assert get_stats(conn) == {
            "videos": 1,
            "shots": 1,
            "keyframes": 1,
            "follow_frames": 1,
            "asr_segments": 0,
        }


def test_partial_reindex_reruns_in_current_generation(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    cfg = _patch_pipeline(tmp_path, monkeypatch, calls)
    build_module.build(cfg)
    calls.clear()

    report = build_module.build(cfg, steps=["follow"], reindex=True)

    assert (report.follow_frames, report.skipped, report.failed) == (1, 0, 0)
    assert calls == ["follow"]
    with closing(connect(cfg.db_path)) as conn:
        assert current_generation(conn, "L21_V001") == 0
        stats = get_stats(conn)
        assert (stats["shots"], stats["keyframes"], stats["follow_frames"]) == (1, 1, 1)


def test_follow_skips_when_keyframe_step_produced_none(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    cfg = _patch_pipeline(tmp_path, monkeypatch, calls)
    monkeypatch.setattr(build_module, "extract_keyframes", lambda *args, **kwargs: [])

    build_module.build(cfg, steps=["shots", "keyframes"])
    report = build_module.build(cfg, steps=["follow"])

    assert (report.follow_frames, report.failed, report.skipped) == (0, 0, 0)
    with closing(connect(cfg.db_path)) as conn:
        assert get_index_status(conn, "L21_V001", 0, "follow") == "done"


def test_follow_without_keyframes_fails_loudly(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    cfg = _patch_pipeline(tmp_path, monkeypatch, calls)

    report = build_module.build(cfg, steps=["follow"])

    assert (report.follow_frames, report.failed, report.skipped) == (0, 1, 0)
    assert "no shots" in report.errors[0]
    with closing(connect(cfg.db_path)) as conn:
        assert get_index_status(conn, "L21_V001", 0, "follow") == "failed"
