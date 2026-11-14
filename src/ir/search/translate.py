from __future__ import annotations

import json
import logging
import os
import threading
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
        if not text or not self.cfg.translate.enabled:
            return text

        with self._lock:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                return cached

        key = gemini_api_key(self.cfg)
        if not key:
            logger.warning("translate: thiếu Gemini API key, dùng query gốc")
            return text

        translated = self._request(text, key).strip()
        if not translated:
            return text

        with self._lock:
            self._cache[text] = translated
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return translated

    def _request(self, text: str, key: str) -> str:
        base = self.cfg.translate.base_url.rstrip("/")
        url = f"{base}/models/{self.cfg.translate.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
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
            with urllib.request.urlopen(
                request, timeout=self.cfg.translate.timeout_sec
            ) as response:
                raw = response.read()
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
