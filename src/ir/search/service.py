from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import closing
from urllib.parse import quote

from ..config import AppConfig
from ..store.db import connect, keyframe_uids_with_objects
from ..store.faiss_store import FaissStore, IndexUnavailableError
from ..types import (
    DresAnswer,
    DresAnswerSet,
    DresPayload,
    Evidence,
    FrameOption,
    Hit,
    SearchResponse,
)
from .encoder import TextEncoder
from .translate import GeminiTranslator

__all__ = ["IndexUnavailableError", "SearchService"]

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self, cfg: AppConfig, translator: GeminiTranslator | None = None
    ) -> None:
        self.cfg = cfg
        self._stores: dict[str, FaissStore] = {}
        self._encoders: dict[str, TextEncoder] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()
        self._translator = translator or GeminiTranslator(cfg)

    def _model_lock(self, name: str) -> threading.Lock:
        with self._registry_lock:
            lock = self._locks.get(name)
            if lock is None:
                lock = threading.Lock()
                self._locks[name] = lock
            return lock

    def _ensure_loaded(
        self, model: str | None = None
    ) -> tuple[FaissStore, TextEncoder, str]:
        profile = self.cfg.embed_profile(model)
        name = profile.name
        store = self._stores.get(name)
        encoder = self._encoders.get(name)
        if store is not None and encoder is not None:
            return store, encoder, name

        with self._model_lock(name):
            store = self._stores.get(name)
            encoder = self._encoders.get(name)
            if store is None:
                if not self.cfg.db_path.is_file():
                    raise IndexUnavailableError(f"Không thấy database: {self.cfg.db_path}")
                directory = self.cfg.embeddings_dir_for(name)
                try:
                    store = FaissStore.load_at(directory)
                except IndexUnavailableError as exc:
                    raise IndexUnavailableError(
                        f"Chưa có embedding index cho model {name!r} "
                        f"({profile.model}): {directory}"
                    ) from exc
                if store.model and store.model != profile.model:
                    raise IndexUnavailableError(
                        f"index model {store.model!r} != profile {profile.model!r}"
                    )
                if store.dim != profile.dim:
                    raise IndexUnavailableError(
                        f"index dim {store.dim} != profile {name!r} dim {profile.dim}"
                    )
                self._stores[name] = store
            if encoder is None:
                fp16 = profile.fp16 if profile.fp16 is not None else self.cfg.embed.fp16
                self._encoders[name] = TextEncoder(
                    profile.model,
                    profile.dim,
                    backend=profile.encoder,
                    fp16=fp16,
                )
            return self._stores[name], self._encoders[name], name

    def models(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for name, profile in self.cfg.embed_profiles().items():
            directory = self.cfg.embeddings_dir_for(name)
            available = (directory / "faiss.index").is_file() and (
                directory / "id_map.npy"
            ).is_file()
            model = profile.model
            count = None
            manifest_path = directory / "manifest.json"
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    model = manifest.get("model") or model
                    count = manifest.get("count")
                except (OSError, ValueError):
                    pass
            entries.append(
                {
                    "name": name,
                    "model": model,
                    "dim": profile.dim,
                    "encoder": profile.encoder,
                    "available": available,
                    "keyframes": int(count) if count is not None else None,
                    "default": name == self.cfg.embed.default,
                }
            )
        entries.sort(key=lambda item: (not bool(item["default"]), str(item["name"])))
        return entries

    def warmup(self) -> None:
        try:
            _, encoder, _ = self._ensure_loaded()
            encoder.encode("warmup")
        except (IndexUnavailableError, ValueError):
            return
        except Exception:
            logger.exception("search warmup failed")

    def search(
        self,
        text: str,
        top_k: int | None = None,
        objects: list[str] | None = None,
        model: str | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        text = text.strip()
        if not text:
            raise ValueError("query rỗng")

        labels = sorted(
            {str(item).strip().lower() for item in (objects or []) if str(item).strip()}
        )
        limit = min(max(top_k or self.cfg.search.top_k, 1), 50)
        store, encoder, model_name = self._ensure_loaded(model)
        query_en = self._translate(text)
        vector = encoder.encode(query_en)

        candidate_k = min(store.count, max(limit * 10, 50))
        while True:
            candidates = store.search(vector, candidate_k)
            if labels:
                candidates = self._filter_candidates(candidates, labels)
            hits = self._build_hits(candidates, limit)
            if not labels or len(hits) >= limit or candidate_k >= store.count:
                break
            candidate_k = min(store.count, candidate_k * 2)

        payload = None
        if hits:
            top = hits[0]
            frame = next(
                (option for option in top.frames if option.is_keyframe),
                top.frames[0] if top.frames else None,
            )
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
            query=text,
            translated_query=query_en,
            model=model_name,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=hits,
            dres_payload=payload,
        )

    def _filter_candidates(
        self, candidates: list[tuple[float, int]], labels: list[str]
    ) -> list[tuple[float, int]]:
        if not candidates:
            return []
        uids = [kf_uid for _, kf_uid in candidates]
        with closing(connect(self.cfg.db_path)) as conn:
            allowed = keyframe_uids_with_objects(conn, uids, labels)
        return [(score, kf_uid) for score, kf_uid in candidates if kf_uid in allowed]

    def _translate(self, text: str) -> str:
        try:
            return self._translator.translate(text)
        except Exception:
            logger.exception("translate failed, dùng query gốc")
            return text

    def _build_hits(self, candidates: list[tuple[float, int]], limit: int) -> list[Hit]:
        if not candidates:
            return []

        kf_uids = [kf_uid for _, kf_uid in candidates]
        placeholders = ",".join("?" for _ in kf_uids)
        with closing(connect(self.cfg.db_path)) as conn:
            rows = conn.execute(
                f"""
                SELECT k.kf_uid, k.video_id, k.generation, k.shot_idx, k.kf_idx,
                       k.ts_ms, k.path, k.objects, k.ocr_text,
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
                        evidence=Evidence(
                            ocr=str(row["ocr_text"] or ""),
                            objects=[
                                label
                                for label in str(row["objects"] or "").split(",")
                                if label
                            ],
                        ),
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
            (int(row["generation"]), str(row["video_id"]), int(row["shot_idx"])) for row in rows
        ]
        frames_by_key: dict[tuple[str, int, int], list] = {}
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
                key = (
                    str(follow_row["video_id"]),
                    int(follow_row["shot_idx"]),
                    int(follow_row["kf_idx"]),
                )
                frames_by_key.setdefault(key, []).append(follow_row)

        window_ms = int(self.cfg.keyframe.follow.window_sec * 1000)
        max_frames = self.cfg.keyframe.follow.max_frames
        options: dict[tuple[str, int], list[FrameOption]] = {}

        for row in rows:
            video_id = str(row["video_id"])
            shot_idx = int(row["shot_idx"])
            kf_idx = int(row["kf_idx"])
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
            frames = [
                FrameOption(
                    ts_ms=ts_ms,
                    start_ms=keyframe_start,
                    end_ms=keyframe_end,
                    url=f"/api/keyframes/{quote(relative)}",
                    is_keyframe=True,
                )
            ]

            for follow_row in frames_by_key.get((video_id, shot_idx, kf_idx), [])[:max_frames]:
                follow_ts = int(follow_row["ts_ms"])
                if follow_ts == ts_ms:
                    continue
                start, end = self._frame_interval(
                    follow_ts, shot_start, shot_end, duration_ms, window_ms
                )
                follow_relative = str(follow_row["path"])
                if follow_relative.startswith("follow_frames/"):
                    follow_relative = follow_relative[len("follow_frames/") :]
                frames.append(
                    FrameOption(
                        ts_ms=follow_ts,
                        start_ms=start,
                        end_ms=end,
                        url=f"/api/frames/{quote(follow_relative)}",
                    )
                )

            options[(video_id, shot_idx)] = sorted(frames, key=lambda item: item.ts_ms)

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
