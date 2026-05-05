from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_live_http(url: str) -> str:
        raise AssertionError(f"Live HTTP is disabled in tests: {url}")

    monkeypatch.setattr("src.chain._request_with_retry", fail_live_http)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_chain_responses(fixtures_dir: Path) -> dict[str, object]:
    return json.loads((fixtures_dir / "mock_chain_responses.json").read_text(encoding="utf-8"))
