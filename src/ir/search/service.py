from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import closing
from urllib.parse import quote

from ..config import AppConfig
from ..store.db import connect
from ..store.faiss_store import FaissStore, IndexUnavailableError
from ..types import DresAnswer, DresAnswerSet, DresPayload, FrameOption, Hit, SearchResponse
from .encoder import TextEncoder

__all__ = ["IndexUnavailableError", "SearchService"]

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._store: FaissStore | None = None
        self._encoder: TextEncoder | None = None
        self._load_lock = threading.Lock()

    def _ensure_loaded(self) -> tuple[FaissStore, TextEncoder]:
        if self._store is not None and self._encoder is not None:
            return self._store, self._encoder

        with self._load_lock:
            if self._store is None:
                if not self.cfg.db_path.is_file():
                    raise IndexUnavailableError(f"Không thấy database: {self.cfg.db_path}")
                store = FaissStore.load(self.cfg)
                if store.model and store.model != self.cfg.embed.model:
                    raise IndexUnavailableError(
                        f"index model {store.model!r} != config {self.cfg.embed.model!r}"
                    )
                if store.dim != self.cfg.embed.dim:
                    raise IndexUnavailableError(
                        f"index dim {store.dim} != config {self.cfg.embed.dim}"
                    )
                self._store = store
            if self._encoder is None:
                self._encoder = TextEncoder(self.cfg.embed.model, self.cfg.embed.dim)
            return self._store, self._encoder

    def warmup(self) -> None:
        try:
            _, encoder = self._ensure_loaded()
            encoder.encode("warmup")
        except IndexUnavailableError:
            return
        except Exception:
            logger.exception("search warmup failed")

    def search(self, text: str, top_k: int | None = None) -> SearchResponse:
        started = time.perf_counter()
        text = text.strip()
        if not text:
            raise ValueError("query rỗng")

        limit = min(max(top_k or self.cfg.search.top_k, 1), 50)
        store, encoder = self._ensure_loaded()
        vector = encoder.encode(text)

        candidate_k = min(store.count, max(limit * 10, 50))
        candidates = store.search(vector, candidate_k)
        hits = self._build_hits(candidates, limit)

        payload = None
        if hits:
            top = hits[0]
            frame = top.frames[0] if top.frames else None
            payload = DresPayload(
                answerSets=[
                    DresAnswerSet(
                        answers=[
                            DresAnswer(
                                media_item_name=top.video_id,
                                start=frame.start_ms if frame else top.start_ms,
                                end=frame.end_ms if frame else top.end_ms,
                            )
                        ]
                    )
                ]
            )

        return SearchResponse(
            query_id=uuid.uuid4().hex,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=hits,
            dres_payload=payload,
        )

    def _build_hits(self, candidates: list[tuple[float, int]], limit: int) -> list[Hit]:
        if not candidates:
            return []

        kf_uids = [kf_uid for _, kf_uid in candidates]
        placeholders = ",".join("?" for _ in kf_uids)
        with closing(connect(self.cfg.db_path)) as conn:
            rows = conn.execute(
                f"""
                SELECT k.kf_uid, k.video_id, k.generation, k.shot_idx, k.ts_ms, k.path,
                       v.duration_ms, s.start_ms, s.end_ms
                FROM keyframes k
                JOIN videos v
                  ON v.video_id = k.video_id AND v.generation = k.generation
                LEFT JOIN shots s
                  ON s.video_id = k.video_id
                 AND s.generation = k.generation
                 AND s.shot_idx = k.shot_idx
                WHERE k.kf_uid IN ({placeholders})
                """,
                kf_uids,
            ).fetchall()

            by_uid = {int(row["kf_uid"]): row for row in rows}
            hits: list[Hit] = []
            hit_rows = []
            seen_shots: set[tuple[str, int]] = set()

            for score, kf_uid in candidates:
                row = by_uid.get(kf_uid)
                if row is None:
                    continue

                shot_key = (str(row["video_id"]), int(row["shot_idx"]))
                if shot_key in seen_shots:
                    continue
                seen_shots.add(shot_key)

                start_ms, end_ms = self._interval(row)
                relative = str(row["path"])
                if relative.startswith("keyframes/"):
                    relative = relative[len("keyframes/") :]

                hits.append(
                    Hit(
                        video_id=str(row["video_id"]),
                        shot_idx=int(row["shot_idx"]),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        score=score,
                        confidence=max(0.0, min(1.0, score)),
                        keyframe_url=f"/api/keyframes/{quote(relative)}",
                    )
                )
                hit_rows.append(row)
                if len(hits) >= limit:
                    break

            options = self._frame_options(conn, hit_rows)

        for hit, row in zip(hits, hit_rows, strict=True):
            hit.frames = options.get((str(row["video_id"]), int(row["shot_idx"])), [])

        return hits

    def _frame_options(self, conn, rows) -> dict[tuple[str, int], list[FrameOption]]:
        keys = [
            (int(row["generation"]), str(row["video_id"]), int(row["shot_idx"]))
            for row in rows
        ]
        frames_by_shot: dict[tuple[str, int], list] = {}
        if keys:
            clauses = " OR ".join(
                "(generation = ? AND video_id = ? AND shot_idx = ?)" for _ in keys
            )
            params = [value for key in keys for value in key]
            follow_rows = conn.execute(
                f"""
                SELECT video_id, shot_idx, kf_idx, frame_idx, ts_ms, path
                FROM follow_frames
                WHERE {clauses}
                ORDER BY shot_idx, ts_ms
                """,
                params,
            ).fetchall()
            for follow_row in follow_rows:
                pair = (str(follow_row["video_id"]), int(follow_row["shot_idx"]))
                frames_by_shot.setdefault(pair, []).append(follow_row)

        window_ms = int(self.cfg.keyframe.follow.window_sec * 1000)
        max_frames = self.cfg.keyframe.follow.max_frames
        options: dict[tuple[str, int], list[FrameOption]] = {}

        for row in rows:
            video_id = str(row["video_id"])
            shot_idx = int(row["shot_idx"])
            ts_ms = int(row["ts_ms"])
            duration_ms = int(row["duration_ms"] or 0)
            shot_start = row["start_ms"]
            shot_end = row["end_ms"]

            relative = str(row["path"])
            if relative.startswith("keyframes/"):
                relative = relative[len("keyframes/") :]

            keyframe_start, keyframe_end = self._frame_interval(
                ts_ms, shot_start, shot_end, duration_ms, window_ms
            )
            options[(video_id, shot_idx)] = [
                FrameOption(
                    ts_ms=ts_ms,
                    start_ms=keyframe_start,
                    end_ms=keyframe_end,
                    url=f"/api/keyframes/{quote(relative)}",
                    is_keyframe=True,
                )
            ]

            follows = [
                follow_row
                for follow_row in frames_by_shot.get((video_id, shot_idx), [])
                if int(follow_row["ts_ms"]) > ts_ms
            ][:max_frames]

            for follow_row in follows:
                follow_ts = int(follow_row["ts_ms"])
                start, end = self._frame_interval(
                    follow_ts, shot_start, shot_end, duration_ms, window_ms
                )
                follow_relative = str(follow_row["path"])
                if follow_relative.startswith("follow_frames/"):
                    follow_relative = follow_relative[len("follow_frames/") :]
                options[(video_id, shot_idx)].append(
                    FrameOption(
                        ts_ms=follow_ts,
                        start_ms=start,
                        end_ms=end,
                        url=f"/api/frames/{quote(follow_relative)}",
                    )
                )

        return options

    @staticmethod
    def _frame_interval(
        ts_ms: int,
        shot_start: int | None,
        shot_end: int | None,
        duration_ms: int,
        window_ms: int,
    ) -> tuple[int, int]:
        half = max(0, window_ms // 2)
        start = ts_ms - half
        end = ts_ms + half
        if shot_start is not None:
            start = max(int(shot_start), start)
        if shot_end is not None:
            end = min(int(shot_end), end)
        if duration_ms > 0:
            end = min(duration_ms, end)
        start = max(0, start)
        if end <= start:
            end = start + max(1, window_ms)
        return start, end

    @staticmethod
    def _interval(row) -> tuple[int, int]:
        ts_ms = int(row["ts_ms"])
        duration_ms = int(row["duration_ms"] or 0)
        shot_start = row["start_ms"]
        shot_end = row["end_ms"]

        if shot_start is not None and shot_end is not None and int(shot_end) > int(shot_start):
            start_ms, end_ms = int(shot_start), int(shot_end)
        else:
            start_ms, end_ms = ts_ms - 1000, ts_ms + 1000

        start_ms = max(0, start_ms)
        if duration_ms > 0:
            end_ms = min(duration_ms, end_ms)
        if end_ms <= start_ms:
            end_ms = start_ms + 2000
        return start_ms, end_ms
