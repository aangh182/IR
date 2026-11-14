from __future__ import annotations

import io
import json
import urllib.error

import pytest

import ir.search.translate as translate_module
from ir.config import AppConfig, TranslateConfig
from ir.search.translate import GeminiTranslator, TranslationError, gemini_api_key


class _Response:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _cfg(tmp_path, **kwargs) -> AppConfig:
    return AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        translate=TranslateConfig(**kwargs),
    )


def test_disabled_returns_original(tmp_path) -> None:
    translator = GeminiTranslator(_cfg(tmp_path, enabled=False))
    assert translator.translate("  người đàn ông  ") == "người đàn ông"


def test_missing_key_returns_original(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    translator = GeminiTranslator(_cfg(tmp_path))
    assert translator.translate("người đàn ông") == "người đàn ông"


def test_translates_vietnamese_and_caches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls: list[dict] = []

    def fake_urlopen(request, timeout=None):
        calls.append(json.loads(request.data.decode("utf-8")))
        return _Response(
            {"candidates": [{"content": {"parts": [{"text": " a man speaking "}]}}]}
        )

    monkeypatch.setattr(translate_module.urllib.request, "urlopen", fake_urlopen)

    translator = GeminiTranslator(_cfg(tmp_path))
    assert translator.translate("một người đàn ông đang nói") == "a man speaking"
    assert translator.translate("một người đàn ông đang nói") == "a man speaking"
    assert len(calls) == 1
    assert calls[0]["contents"][0]["parts"][0]["text"] == "một người đàn ông đang nói"


def test_api_key_from_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cfg = _cfg(tmp_path)
    cfg.state_root.mkdir(parents=True)
    (cfg.state_root / "gemini_api_key").write_text("file-key\n", encoding="utf-8")

    assert gemini_api_key(cfg) == "file-key"


def test_http_error_raises_translation_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"error": "bad"}')
        )

    monkeypatch.setattr(translate_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(TranslationError):
        GeminiTranslator(_cfg(tmp_path)).translate("xin chào")


def test_blocked_response_raises_translation_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_urlopen(request, timeout=None):
        return _Response({"promptFeedback": {"blockReason": "SAFETY"}})

    monkeypatch.setattr(translate_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(TranslationError):
        GeminiTranslator(_cfg(tmp_path)).translate("xin chào")
