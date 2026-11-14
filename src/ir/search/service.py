from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from contextlib import closing
from urllib.parse import quote

import faiss
import numpy as np

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
        self._boilerplate: dict[str, set[int] | None] = {}
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
            if name not in self._boilerplate:
                self._boilerplate[name] = self._load_boilerplate(name, store)
            if encoder is None:
                fp16 = profile.fp16 if profile.fp16 is not None else self.cfg.embed.fp16
                self._encoders[name] = TextEncoder(
                    profile.model,
                    profile.dim,
                    backend=profile.encoder,
                    fp16=fp16,
                )
            return self._stores[name], self._encoders[name], name

    def _load_boilerplate(self, name: str, store: FaissStore) -> set[int] | None:
        if not self.cfg.boilerplate.enabled:
            return None
        path = self.cfg.boilerplate_mask_path_for(name)
        if not path.is_file():
            return None
        try:
            mask = np.load(path)
        except (OSError, ValueError):
            logger.exception("failed to load boilerplate mask %s", path)
            return None
        if mask.shape != (store.count,):
            logger.warning(
                "boilerplate mask %s shape %s != index %s for %s",
                path,
                mask.shape,
                store.count,
                name,
            )
            return None
        meta_path = self.cfg.boilerplate_meta_path_for(name)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            expected = meta.get("id_map_sha256")
            if expected:
                actual = hashlib.sha256(store.id_map.tobytes()).hexdigest()
                if actual != expected:
                    logger.warning(
                        "boilerplate mask %s is stale for %s (id_map changed)",
                        path,
                        name,
                    )
                    return None
        return set(store.id_map[np.asarray(mask, dtype=bool)].tolist())

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
            boilerplate = None
            meta_path = self.cfg.boilerplate_meta_path_for(name)
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    value = meta.get("boilerplate")
                    if isinstance(value, (int, float)):
                        boilerplate = int(value)
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
                    "boilerplate": boilerplate,
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
        include_boilerplate: bool = False,
        dedup: bool | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        text = text.strip()
        if not text:
            raise ValueError("query rỗng")

        limit = min(max(top_k or self.cfg.search.top_k, 1), 50)
        store, encoder, model_name = self._ensure_loaded(model)
        boilerplate = self._boilerplate.get(model_name)
        use_dedup = self.cfg.search.dedup if dedup is None else dedup
        query_en = self._translate(text)
        vector = encoder.encode(query_en)
        hits = self._search_candidates(
            store,
            vector,
            limit,
            self._normalize_labels(objects),
            boilerplate,
            include_boilerplate,
            use_dedup,
        )

        return SearchResponse(
            query_id=uuid.uuid4().hex,
            query=text,
            translated_query=query_en,
            model=model_name,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=hits,
            dres_payload=self._build_payload(hits),
        )

    def search_similar(
        self,
        kf_uid: int,
        top_k: int | None = None,
        objects: list[str] | None = None,
        model: str | None = None,
        include_boilerplate: bool = False,
        dedup: bool | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        limit = min(max(top_k or self.cfg.search.top_k, 1), 50)
        store, _, model_name = self._ensure_loaded(model)
        try:
            vector = store.vectors_for([int(kf_uid)])[0]
        except KeyError as exc:
            raise ValueError(
                f"kf_uid {kf_uid} không có trong index {model_name!r}"
            ) from exc

        boilerplate = self._boilerplate.get(model_name)
        use_dedup = self.cfg.search.dedup if dedup is None else dedup
        hits = self._search_candidates(
            store,
            vector,
            limit,
            self._normalize_labels(objects),
            boilerplate,
            include_boilerplate,
            use_dedup,
            exclude_kf_uid=int(kf_uid),
        )
        source = self._keyframe_label(int(kf_uid))

        return SearchResponse(
            query_id=uuid.uuid4().hex,
            query=f"similar:{source}" if source else f"similar:{kf_uid}",
            model=model_name,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=hits,
            dres_payload=self._build_payload(hits),
        )

    def timeline(
        self,
        kf_uid: int,
        before: int | None = None,
        after: int | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        before = self.cfg.search.timeline_before if before is None else before
        after = self.cfg.search.timeline_after if after is None else after
        if before < 0 or after < 0:
            raise ValueError("before/after phải >= 0")

        with closing(connect(self.cfg.db_path)) as conn:
            row = conn.execute(
                "SELECT video_id, generation, ts_ms FROM keyframes WHERE kf_uid = ?",
                (int(kf_uid),),
            ).fetchone()
            if row is None:
                raise ValueError(f"kf_uid {kf_uid} không tồn tại")
            video_id = str(row["video_id"])
            generation = int(row["generation"])
            rows = conn.execute(
                """
                SELECT kf_uid FROM keyframes
                WHERE video_id = ? AND generation = ?
                ORDER BY shot_idx, kf_idx, ts_ms
                """,
                (video_id, generation),
            ).fetchall()

        ids = [int(item["kf_uid"]) for item in rows]
        try:
            position = ids.index(int(kf_uid))
        except ValueError as exc:
            raise ValueError(
                f"kf_uid {kf_uid} không có trong video {video_id}"
            ) from exc

        target = max(1, before + 1 + after)
        start = max(0, position - before)
        if start + target > len(ids):
            start = max(0, len(ids) - target)
        window = ids[start : start + target]

        hits = self._build_hits(
            [(0.0, uid) for uid in window],
            len(window),
            dedup_shots=False,
        )
        source = next((hit for hit in hits if hit.kf_uid == int(kf_uid)), None)

        return SearchResponse(
            query_id=uuid.uuid4().hex,
            query=f"timeline:{video_id}@{int(row['ts_ms'])}",
            model="",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=hits,
            dres_payload=self._build_payload([source]) if source else None,
        )

    def _search_candidates(
        self,
        store: FaissStore,
        vector: np.ndarray,
        limit: int,
        labels: list[str],
        boilerplate: set[int] | None,
        include_boilerplate: bool,
        use_dedup: bool,
        exclude_kf_uid: int | None = None,
    ) -> list[Hit]:
        filtering = (
            bool(labels)
            or (bool(boilerplate) and not include_boilerplate)
            or use_dedup
        )
        candidate_k = min(store.count, max(limit * 10, 50))
        while True:
            candidates = store.search(vector, candidate_k)
            if exclude_kf_uid is not None:
                candidates = [
                    (score, kf_uid)
                    for score, kf_uid in candidates
                    if kf_uid != exclude_kf_uid
                ]
            if labels:
                candidates = self._filter_candidates(candidates, labels)
            if boilerplate and not include_boilerplate:
                candidates = [
                    (score, kf_uid)
                    for score, kf_uid in candidates
                    if kf_uid not in boilerplate
                ]
            if use_dedup:
                candidates = self._dedup_candidates(store, candidates, limit)
            hits = self._build_hits(candidates, limit, boilerplate)
            if not filtering or len(hits) >= limit or candidate_k >= store.count:
                break
            candidate_k = min(store.count, candidate_k * 2)
        return hits

    @staticmethod
    def _normalize_labels(objects: list[str] | None) -> list[str]:
        return sorted(
            {str(item).strip().lower() for item in (objects or []) if str(item).strip()}
        )

    def _keyframe_label(self, kf_uid: int) -> str:
        with closing(connect(self.cfg.db_path)) as conn:
            row = conn.execute(
                "SELECT video_id, ts_ms FROM keyframes WHERE kf_uid = ?", (kf_uid,)
            ).fetchone()
        if row is None:
            return ""
        return f"{row['video_id']}@{int(row['ts_ms'])}"

    @staticmethod
    def _build_payload(hits: list[Hit]) -> DresPayload | None:
        if not hits:
            return None
        top = hits[0]
        frame = next(
            (option for option in top.frames if option.is_keyframe),
            top.frames[0] if top.frames else None,
        )
        return DresPayload(
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

    def _dedup_candidates(
        self,
        store: FaissStore,
        candidates: list[tuple[float, int]],
        limit: int,
    ) -> list[tuple[float, int]]:
        if not candidates:
            return []
        pool_size = min(len(candidates), max(limit * 10, 200))
        pool = candidates[:pool_size]
        try:
            vectors = store.vectors_for([kf_uid for _, kf_uid in pool])
        except Exception:
            logger.exception("dedup skipped: cannot reconstruct vectors")
            return candidates
        if len(vectors) != len(pool):
            return candidates
        faiss.normalize_L2(vectors)

        selected: list[tuple[float, int]] = []
        selected_rows: list[int] = []
        target = limit * 2
        for row, candidate in enumerate(pool):
            if len(selected) >= target:
                break
            if selected_rows and (
                float(np.max(vectors[selected_rows] @ vectors[row]))
                > self.cfg.search.dedup_threshold
            ):
                continue
            selected.append(candidate)
            selected_rows.append(row)
        return selected

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

    def _build_hits(
        self,
        candidates: list[tuple[float, int]],
        limit: int,
        boilerplate: set[int] | None = None,
        dedup_shots: bool = True,
    ) -> list[Hit]:
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

                if dedup_shots:
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
                        kf_uid=kf_uid,
                        keyframe_url=f"/api/keyframes/{quote(relative)}",
                        is_boilerplate=bool(boilerplate and kf_uid in boilerplate),
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
