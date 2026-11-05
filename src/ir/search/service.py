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
from ..types import DresAnswer, DresAnswerSet, DresPayload, Hit, SearchResponse
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
            payload = DresPayload(
                answerSets=[
                    DresAnswerSet(
                        answers=[
                            DresAnswer(
                                media_item_name=top.video_id,
                                start=top.start_ms,
                                end=top.end_ms,
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
                SELECT k.kf_uid, k.video_id, k.shot_idx, k.ts_ms, k.path,
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
            if len(hits) >= limit:
                break

        return hits

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
