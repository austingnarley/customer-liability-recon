from __future__ import annotations

from decimal import Decimal

import pytest

from src.reconcile import reconcile


def test_reconcile_status_thresholds(tmp_path, mocker) -> None:
    ledger = _write_ledger(tmp_path, "BTC", "100.00000000")
    wallets = _write_wallets(tmp_path)
    prices = _write_prices(tmp_path)
    mocker.patch("src.chain.fetch_btc_balance", side_effect=[Decimal("100.5")])
    mocker.patch("src.chain.fetch_eth_balance", return_value=Decimal("0"))
    mocker.patch("src.chain.fetch_erc20_balance", return_value=Decimal("0"))

    ok_row = reconcile(ledger, wallets, prices)[0]

    assert ok_row.status == "OK"
    assert ok_row.coverage_ratio == Decimal("1.005")

    mocker.patch("src.chain.fetch_btc_balance", side_effect=[Decimal("99.5")])
    watch_row = reconcile(ledger, wallets, prices)[0]

    assert watch_row.status == "WATCH"
    assert watch_row.coverage_ratio == Decimal("0.995")

    mocker.patch("src.chain.fetch_btc_balance", side_effect=[Decimal("98")])
    breach_row = reconcile(ledger, wallets, prices)[0]

    assert breach_row.status == "BREACH"
    assert breach_row.coverage_ratio == Decimal("0.98")


def test_usd_value_at_risk_calculation(tmp_path, mocker) -> None:
    ledger = _write_ledger(tmp_path, "BTC", "100.00000000")
    wallets = _write_wallets(tmp_path)
    prices = _write_prices(tmp_path)
    mocker.patch("src.chain.fetch_btc_balance", return_value=Decimal("98"))
    mocker.patch("src.chain.fetch_eth_balance", return_value=Decimal("0"))
    mocker.patch("src.chain.fetch_erc20_balance", return_value=Decimal("0"))

    row = reconcile(ledger, wallets, prices)[0]

    assert row.usd_value_at_risk == Decimal("135000.00000000")


def test_missing_asset_in_wallet_config_raises_helpful_error(tmp_path, mocker) -> None:
    ledger = _write_ledger(tmp_path, "BTC", "100.00000000")
    wallets = tmp_path / "wallets.yaml"
    wallets.write_text("BTC:\n  - btc-address\n", encoding="utf-8")
    prices = _write_prices(tmp_path)
    mocker.patch("src.chain.fetch_btc_balance", return_value=Decimal("100"))

    with pytest.raises(ValueError, match="Wallet config is missing assets"):
        reconcile(ledger, wallets, prices)


def test_coverage_ratio_is_none_when_liabilities_are_zero(tmp_path, mocker) -> None:
    ledger = _write_ledger(tmp_path, "BTC", "100.00000000")
    wallets = _write_wallets(tmp_path)
    prices = _write_prices(tmp_path)
    mocker.patch("src.chain.fetch_btc_balance", return_value=Decimal("100"))
    mocker.patch("src.chain.fetch_eth_balance", return_value=Decimal("1"))
    mocker.patch("src.chain.fetch_erc20_balance", return_value=Decimal("1"))

    rows = reconcile(ledger, wallets, prices)
    eth_row = next(row for row in rows if row.asset == "ETH")

    assert eth_row.customer_liabilities == Decimal("0")
    assert eth_row.coverage_ratio is None
    assert eth_row.status == "OK"


def _write_ledger(tmp_path, asset: str, balance: str):
    path = tmp_path / "ledger.csv"
    path.write_text(
        f"customer_id,asset,balance,as_of\nC-000001,{asset},{balance},2026-05-05\n",
        encoding="utf-8",
    )
    return path


def _write_wallets(tmp_path):
    path = tmp_path / "wallets.yaml"
    path.write_text(
        """
BTC:
  - btc-address
ETH:
  - eth-address
USDC:
  - usdc-address
USDT:
  - usdt-address
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_prices(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(
        """
asset,usd_price,as_of
BTC,67500.00,2026-05-05
ETH,3100.00,2026-05-05
USDC,1.00,2026-05-05
USDT,1.00,2026-05-05
""".strip(),
        encoding="utf-8",
    )
    return path
