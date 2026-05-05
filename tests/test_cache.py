from __future__ import annotations

import time

from src.cache import ResponseCache


def test_response_cache_returns_unexpired_value(tmp_path) -> None:
    cache = ResponseCache(tmp_path / "responses.db")

    cache.set("key", "payload", ttl_seconds=60)

    assert cache.get("key") == "payload"


def test_response_cache_expires_value(tmp_path) -> None:
    cache = ResponseCache(tmp_path / "responses.db")

    cache.set("key", "payload", ttl_seconds=0)
    time.sleep(0.01)

    assert cache.get("key") is None
