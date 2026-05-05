from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ASSETS = ("BTC", "ETH", "USDC", "USDT")
HOLDER_RATES = {"BTC": 0.40, "ETH": 0.50, "USDC": 0.60, "USDT": 0.30}
TARGET_TOTALS = {
    "BTC": Decimal("140"),
    "ETH": Decimal("8400"),
    "USDC": Decimal("12400000"),
    "USDT": Decimal("4200000"),
}
BALANCE_QUANTUM = {
    "BTC": Decimal("0.00000001"),
    "ETH": Decimal("0.00000001"),
    "USDC": Decimal("0.01"),
    "USDT": Decimal("0.01"),
}
REQUIRED_COLUMNS = ["customer_id", "asset", "balance", "as_of"]


def generate_ledger(*, customers: int, seed: int, as_of: date, out_path: Path) -> None:
    """Generate a deterministic synthetic customer ledger CSV."""
    rng = np.random.default_rng(seed)
    customer_ids = [f"C-{idx:06d}" for idx in range(1, customers + 1)]
    rows: list[dict[str, str]] = []

    for asset in ASSETS:
        holder_count = int(round(customers * HOLDER_RATES[asset]))
        holder_indexes = rng.choice(customers, holder_count, replace=False)
        holder_ids = [customer_ids[idx] for idx in holder_indexes]
        balances = _synthetic_balances(asset, holder_count, rng)
        rows.extend(
            {
                "customer_id": customer_id,
                "asset": asset,
                "balance": _format_decimal(balance, asset),
                "as_of": as_of.isoformat(),
            }
            for customer_id, balance in zip(holder_ids, balances, strict=True)
        )

    ledger = pd.DataFrame(rows, columns=REQUIRED_COLUMNS).sort_values(["customer_id", "asset"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out_path, index=False)


def load_liabilities(path: Path) -> pd.DataFrame:
    """Load and validate the long-form customer liability ledger."""
    ledger = pd.read_csv(
        path,
        dtype={"customer_id": "string", "asset": "string", "balance": "string", "as_of": "string"},
    )
    missing = set(REQUIRED_COLUMNS) - set(ledger.columns)
    if missing:
        raise ValueError(f"Ledger is missing required columns: {sorted(missing)}")
    ledger = ledger[REQUIRED_COLUMNS].copy()
    invalid_assets = sorted(set(ledger["asset"].dropna()) - set(ASSETS))
    if invalid_assets:
        raise ValueError(f"Ledger contains unsupported assets: {invalid_assets}")
    ledger["balance"] = ledger["balance"].map(lambda value: Decimal(str(value)))
    if ledger["balance"].map(lambda value: value < 0).any():
        raise ValueError("Ledger contains negative balances")
    return ledger


def aggregate_by_asset(ledger: pd.DataFrame) -> pd.DataFrame:
    """Aggregate liabilities by asset using the DuckDB SQL query."""
    sql_path = Path(__file__).parent / "sql" / "liability_summary.sql"
    sql = sql_path.read_text(encoding="utf-8")
    query_input = ledger.copy()
    query_input["balance"] = query_input["balance"].map(str)
    with duckdb.connect(database=":memory:") as conn:
        conn.register("ledger", query_input)
        summary = conn.execute(sql).fetchdf()
    summary["total_balance"] = summary["total_balance"].map(lambda value: Decimal(str(value)))
    summary["top_1pct_share"] = summary["top_1pct_share"].map(lambda value: Decimal(str(value)))
    summary["customer_count"] = summary["customer_count"].astype(int)
    return summary.set_index("asset")


def _synthetic_balances(asset: str, holder_count: int, rng: np.random.Generator) -> list[Decimal]:
    target = TARGET_TOTALS[asset]
    top_count = max(1, int(round(holder_count * 0.01)))
    top_target = target * Decimal("0.40")
    rest_target = target - top_target

    top_raw = rng.lognormal(mean=2.0, sigma=0.9, size=top_count)
    rest_raw = rng.lognormal(mean=0.0, sigma=1.1, size=holder_count - top_count)
    balances = _scale_to_decimals(top_raw, top_target, asset) + _scale_to_decimals(
        rest_raw,
        rest_target,
        asset,
    )
    rng.shuffle(balances)
    return balances


def _scale_to_decimals(raw: np.ndarray, target: Decimal, asset: str) -> list[Decimal]:
    quantum = BALANCE_QUANTUM[asset]
    raw_total = Decimal(str(raw.sum()))
    scaled = [
        (Decimal(str(value)) / raw_total * target).quantize(quantum, rounding=ROUND_DOWN)
        for value in raw
    ]
    drift = target - sum(scaled, Decimal("0"))
    if scaled and drift > 0:
        scaled[0] += drift.quantize(quantum, rounding=ROUND_DOWN)
    return scaled


def _format_decimal(value: Decimal, asset: str) -> str:
    return f"{value.quantize(BALANCE_QUANTUM[asset]):f}"
