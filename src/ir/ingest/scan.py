from __future__ import annotations

import logging
from pathlib import Path

import av

from ..types import Video

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"}


def _container_duration_ms(container: av.container.InputContainer) -> int:
    if container.duration is not None:
        return int(round(container.duration / av.time_base * 1000))
    stream = next((s for s in container.streams if s.type == "video"), None)
    if stream is not None and stream.duration is not None and stream.time_base is not None:
        return int(round(float(stream.duration * stream.time_base) * 1000))
    return 0


def probe_video(path: str | Path) -> Video:
    source = Path(path)
    with av.open(str(source)) as container:
        video_stream = next((s for s in container.streams if s.type == "video"), None)
        if video_stream is None:
            raise ValueError(f"no video stream: {source}")
        return Video(
            video_id=source.stem,
            path=str(source),
            duration_ms=_container_duration_ms(container),
            fps=float(video_stream.average_rate) if video_stream.average_rate else None,
            width=video_stream.width,
            height=video_stream.height,
            has_audio=any(s.type == "audio" for s in container.streams),
        )


def scan_corpus(corpus_dir: str | Path) -> list[Video]:
    root = Path(corpus_dir)
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )

    videos: list[Video] = []
    seen: dict[str, Path] = {}
    for path in files:
        try:
            video = probe_video(path)
        except Exception as exc:
            logger.warning("skip unreadable video %s: %s", path, exc)
            continue
        previous = seen.get(video.video_id)
        if previous is not None:
            raise ValueError(f"duplicate video_id {video.video_id!r}: {previous} and {path}")
        seen[video.video_id] = path
        videos.append(video)
    return videos
