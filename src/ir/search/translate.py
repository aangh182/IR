from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from ..config import AppConfig

__all__ = ["GeminiTranslator", "TranslationError", "gemini_api_key"]

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You translate Vietnamese search queries into English for a CLIP-based video retrieval system. "
    "Return only the English translation, with no quotes, notes, or explanations. "
    "If the query is already English, return it unchanged."
)

BATCH_SYSTEM_PROMPT = (
    "You translate Vietnamese search queries into English for a CLIP-based video retrieval system. "
    "Return only a JSON array of strings with the translations in the same order "
    "and length as the input. "
    "No notes, no markdown, no explanations. If a query is already English, return it unchanged."
)

MAX_OUTPUT_TOKENS = 512
CACHE_SIZE = 256


class TranslationError(RuntimeError):
    pass


def gemini_api_key(cfg: AppConfig) -> str | None:
    env_name = cfg.translate.api_key_env or "GEMINI_API_KEY"
    return (
        os.environ.get(env_name)
        or os.environ.get("GOOGLE_API_KEY")
        or cfg.translate.api_key
        or _key_from_file(cfg)
    )


class GeminiTranslator:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        if not self.cfg.translate.enabled:
            raise TranslationError("Translate đang tắt; bật translate.enabled để tìm kiếm.")

        with self._lock:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                return cached

        key = gemini_api_key(self.cfg)
        if not key:
            raise TranslationError("Thiếu Gemini API key để dịch query.")

        translated = self._request(text, key).strip()
        if not translated:
            raise TranslationError("Gemini trả về bản dịch rỗng")

        with self._lock:
            self._cache[text] = translated
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return translated

    def translate_many(self, texts: list[str]) -> list[str]:
        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return cleaned
        if not self.cfg.translate.enabled:
            raise TranslationError("Translate đang tắt; bật translate.enabled để tìm kiếm.")

        results: list[str | None] = [None] * len(cleaned)
        missing: list[str] = []
        with self._lock:
            for index, text in enumerate(cleaned):
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    results[index] = cached
                elif text not in missing:
                    missing.append(text)

        def finish(mapping: dict[str, str]) -> list[str]:
            return [
                result if result is not None else mapping.get(cleaned[index], cleaned[index])
                for index, result in enumerate(results)
            ]

        if not missing:
            return finish({})

        key = gemini_api_key(self.cfg)
        if not key:
            raise TranslationError("Thiếu Gemini API key để dịch query.")

        try:
            translated = self._request_batch(missing, key)
        except TranslationError as exc:
            logger.warning("batch translate failed (%s); translating individually", exc)
            translated = [self.translate(text) for text in missing]

        mapping = dict(zip(missing, translated, strict=False))
        with self._lock:
            for text in missing:
                value = mapping.get(text)
                if not value:
                    continue
                self._cache[text] = value
                while len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
        return finish(mapping)

    def _request_batch(self, texts: list[str], key: str) -> list[str]:
        raw = self._request(
            json.dumps(texts, ensure_ascii=False),
            key,
            system=BATCH_SYSTEM_PROMPT,
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise TranslationError("Gemini trả về danh sách dịch không phải JSON") from exc
        if not isinstance(parsed, list) or len(parsed) != len(texts):
            raise TranslationError("Gemini trả về danh sách dịch sai độ dài")
        result = [str(item).strip() for item in parsed]
        if any(not item for item in result):
            raise TranslationError("Gemini trả về bản dịch rỗng")
        return result

    def _request(self, text: str, key: str, system: str = SYSTEM_PROMPT) -> str:
        base = self.cfg.translate.base_url.rstrip("/")
        url = f"{base}/models/{self.cfg.translate.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )

        try:
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(
                        request, timeout=self.cfg.translate.timeout_sec
                    ) as response:
                        raw = response.read()
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code in {429, 503} and attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise
                except TimeoutError as exc:
                    if attempt < 2:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    raise TranslationError("Gemini timeout khi dịch query") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise TranslationError(f"Gemini HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TranslationError(f"Không kết nối được Gemini: {exc.reason}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise TranslationError("Gemini trả về dữ liệu không phải JSON") from exc

        candidates = payload.get("candidates") or []
        if not candidates:
            reason = (payload.get("promptFeedback") or {}).get("blockReason")
            raise TranslationError(f"Gemini không trả về kết quả ({reason or 'empty'})")

        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        translated = "".join(
            str(part.get("text", "")) for part in parts if isinstance(part, dict)
        )
        if not translated.strip():
            raise TranslationError("Gemini trả về bản dịch rỗng")
        return translated


def _key_from_file(cfg: AppConfig) -> str | None:
    path = cfg.state_root / "gemini_api_key"
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None
