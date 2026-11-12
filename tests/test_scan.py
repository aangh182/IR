from __future__ import annotations

from pathlib import Path

import pytest

import ir.ingest.scan as scan_module
from ir.types import Video


def test_scan_skips_unreadable_files(tmp_path, monkeypatch) -> None:
    (tmp_path / "good.mp4").write_bytes(b"x")
    (tmp_path / "bad.mp4").write_bytes(b"x")

    def fake_probe(path: str | Path) -> Video:
        if Path(path).name == "bad.mp4":
            raise ValueError("broken container")
        return Video(video_id="good", path=str(path), duration_ms=1000)

    monkeypatch.setattr(scan_module, "probe_video", fake_probe)

    videos = scan_module.scan_corpus(tmp_path)

    assert [video.video_id for video in videos] == ["good"]


def test_scan_rejects_duplicate_video_ids(tmp_path, monkeypatch) -> None:
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "same.mp4").write_bytes(b"x")

    monkeypatch.setattr(
        scan_module,
        "probe_video",
        lambda path: Video(video_id="same", path=str(path), duration_ms=1000),
    )

    with pytest.raises(ValueError, match="duplicate video_id"):
        scan_module.scan_corpus(tmp_path)
