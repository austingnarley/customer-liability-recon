from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from src.ledger import aggregate_by_asset, generate_ledger, load_liabilities


def test_generate_ledger_produces_expected_schema_and_row_count(tmp_path) -> None:
    out_path = tmp_path / "ledger.csv"
    generate_ledger(customers=100, seed=42, as_of=date(2026, 5, 5), out_path=out_path)

    ledger = pd.read_csv(out_path)

    assert list(ledger.columns) == ["customer_id", "asset", "balance", "as_of"]
    assert len(ledger) == 180
    assert set(ledger["asset"]) == {"BTC", "ETH", "USDC", "USDT"}


def test_generate_ledger_same_seed_is_identical(tmp_path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    generate_ledger(customers=100, seed=42, as_of=date(2026, 5, 5), out_path=first)
    generate_ledger(customers=100, seed=42, as_of=date(2026, 5, 5), out_path=second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_aggregate_by_asset_matches_hand_computed_output() -> None:
    ledger = pd.DataFrame(
        [
            {
                "customer_id": "C-000001",
                "asset": "BTC",
                "balance": Decimal("10"),
                "as_of": "2026-05-05",
            },
            {
                "customer_id": "C-000002",
                "asset": "BTC",
                "balance": Decimal("5"),
                "as_of": "2026-05-05",
            },
            {
                "customer_id": "C-000003",
                "asset": "ETH",
                "balance": Decimal("100"),
                "as_of": "2026-05-05",
            },
            {
                "customer_id": "C-000004",
                "asset": "ETH",
                "balance": Decimal("50"),
                "as_of": "2026-05-05",
            },
        ]
    )

    summary = aggregate_by_asset(ledger)

    assert summary.loc["BTC", "total_balance"] == Decimal("15.000000000000")
    assert summary.loc["BTC", "customer_count"] == 2
    assert summary.loc["BTC", "top_1pct_share"] == Decimal("0.6666666666666666")
    assert summary.loc["ETH", "total_balance"] == Decimal("150.000000000000")
    assert summary.loc["ETH", "customer_count"] == 2
    assert summary.loc["ETH", "top_1pct_share"] == Decimal("0.6666666666666666")


def test_load_liabilities_validates_schema(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("customer_id,asset,balance\nC-000001,BTC,1.0\n", encoding="utf-8")

    try:
        load_liabilities(path)
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("Expected schema validation to fail")
