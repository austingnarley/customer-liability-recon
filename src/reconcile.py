from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml

from src import chain
from src.ledger import ASSETS, aggregate_by_asset, load_liabilities
from src.prices import load_prices

Status = Literal["OK", "WATCH", "BREACH"]


@dataclass(frozen=True)
class ReserveDetail:
    asset: str
    address: str
    balance: Decimal


@dataclass(frozen=True)
class ReconciliationRow:
    asset: str
    customer_liabilities: Decimal
    customer_count: int
    on_chain_reserves: Decimal
    delta: Decimal
    coverage_ratio: Decimal | None
    usd_price: Decimal
    usd_value_at_risk: Decimal
    status: Status
    reserve_details: list[ReserveDetail] = field(default_factory=list)


def reconcile(
    ledger_path: Path,
    wallets_config: Path,
    prices_path: Path,
) -> list[ReconciliationRow]:
    """Run the full reconciliation by comparing liabilities to live on-chain reserves."""
    ledger = load_liabilities(ledger_path)
    liabilities = aggregate_by_asset(ledger)
    wallets = _load_wallets(wallets_config)
    prices = load_prices(prices_path)
    missing_wallet_assets = sorted(set(ASSETS) - set(wallets))
    if missing_wallet_assets:
        raise ValueError(f"Wallet config is missing assets: {missing_wallet_assets}")

    rows: list[ReconciliationRow] = []
    for asset in ASSETS:
        liability = Decimal("0")
        customer_count = 0
        if asset in liabilities.index:
            liability = Decimal(str(liabilities.loc[asset, "total_balance"]))
            customer_count = int(liabilities.loc[asset, "customer_count"])

        reserve_details = _fetch_reserve_details(asset, wallets[asset])
        reserves = sum((detail.balance for detail in reserve_details), Decimal("0"))
        delta = reserves - liability
        coverage_ratio = None if liability == 0 else reserves / liability
        usd_price = prices.get(asset)
        if usd_price is None:
            raise ValueError(f"Price snapshot is missing asset {asset}")
        usd_value_at_risk = max(Decimal("0"), liability - reserves) * usd_price
        rows.append(
            ReconciliationRow(
                asset=asset,
                customer_liabilities=liability,
                customer_count=customer_count,
                on_chain_reserves=reserves,
                delta=delta,
                coverage_ratio=coverage_ratio,
                usd_price=usd_price,
                usd_value_at_risk=usd_value_at_risk,
                status=_status_for(coverage_ratio),
                reserve_details=reserve_details,
            )
        )
    return rows


def _load_wallets(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    if not isinstance(payload, dict):
        raise ValueError("Wallet config must be a mapping of asset to wallet addresses")
    wallets: dict[str, list[str]] = {}
    for asset, addresses in payload.items():
        if not isinstance(asset, str) or not isinstance(addresses, list):
            raise ValueError("Wallet config must map asset symbols to lists of addresses")
        wallets[asset] = [str(address) for address in addresses]
    return wallets


def _fetch_reserve_details(asset: str, addresses: list[str]) -> list[ReserveDetail]:
    details: list[ReserveDetail] = []
    for address in addresses:
        if asset == "BTC":
            balance = chain.fetch_btc_balance(address)
        elif asset == "ETH":
            balance = chain.fetch_eth_balance(address)
        else:
            balance = chain.fetch_erc20_balance(address, asset)
        details.append(ReserveDetail(asset=asset, address=address, balance=balance))
    return details


def _status_for(coverage_ratio: Decimal | None) -> Status:
    if coverage_ratio is None or coverage_ratio >= Decimal("1.000"):
        return "OK"
    if coverage_ratio >= Decimal("0.99"):
        return "WATCH"
    return "BREACH"
