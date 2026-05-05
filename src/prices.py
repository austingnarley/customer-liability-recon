from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"asset", "usd_price", "as_of"}


def load_prices(path: Path) -> dict[str, Decimal]:
    prices = pd.read_csv(path, dtype={"asset": "string", "usd_price": "string", "as_of": "string"})
    missing = REQUIRED_COLUMNS - set(prices.columns)
    if missing:
        raise ValueError(f"Price snapshot is missing required columns: {sorted(missing)}")
    return {str(row.asset): Decimal(str(row.usd_price)) for row in prices.itertuples(index=False)}
