from __future__ import annotations

import json
import os
import threading
import time
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.cache import ResponseCache

MEMPOOL_ADDRESS_URL = "https://mempool.space/api/address/{address}"
ETHERSCAN_URL = "https://api.etherscan.io/v2/api"
DEFAULT_CACHE = ResponseCache(Path(".cache/responses.db"))
DEFAULT_TTL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 20
TOKEN_CONTRACTS = {
    "USDC": ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", Decimal("1000000")),
    "USDT": ("0xdAC17F958D2ee523a2206206994597C13D831ec7", Decimal("1000000")),
}

_SESSION = requests.Session()
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_MIN_INTERVAL_SECONDS = 0.2


class ChainFetchError(RuntimeError):
    """Raised when a chain balance cannot be fetched after retries."""


class RetryableHTTPError(RuntimeError):
    """Internal exception for retryable HTTP status codes."""


def fetch_btc_balance(address: str) -> Decimal:
    """Return BTC balance in BTC using mempool.space."""
    url = MEMPOOL_ADDRESS_URL.format(address=address)
    try:
        payload = _get_json(url)
        chain_stats = payload["chain_stats"]
        mempool_stats = payload.get("mempool_stats", {})
        sats = (
            int(chain_stats.get("funded_txo_sum", 0))
            - int(chain_stats.get("spent_txo_sum", 0))
            + int(mempool_stats.get("funded_txo_sum", 0))
            - int(mempool_stats.get("spent_txo_sum", 0))
        )
        return Decimal(sats) / Decimal("100000000")
    except Exception as exc:
        raise ChainFetchError(f"Failed to fetch BTC balance for address {address}: {exc}") from exc


def fetch_eth_balance(address: str) -> Decimal:
    """Return ETH balance in ETH using Etherscan."""
    try:
        result = _etherscan_account_call(
            {
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
            }
        )
        return Decimal(result) / Decimal("1000000000000000000")
    except Exception as exc:
        raise ChainFetchError(f"Failed to fetch ETH balance for address {address}: {exc}") from exc


def fetch_erc20_balance(address: str, token: str) -> Decimal:
    """Return ERC-20 token balance in token units using Etherscan."""
    token_symbol = token.upper()
    if token_symbol not in TOKEN_CONTRACTS:
        raise ChainFetchError(f"Unsupported ERC-20 token {token} for address {address}")

    contract_address, divisor = TOKEN_CONTRACTS[token_symbol]
    try:
        result = _etherscan_account_call(
            {
                "module": "account",
                "action": "tokenbalance",
                "contractaddress": contract_address,
                "address": address,
                "tag": "latest",
            }
        )
        return Decimal(result) / divisor
    except Exception as exc:
        raise ChainFetchError(
            f"Failed to fetch {token_symbol} balance for address {address}: {exc}"
        ) from exc


def _etherscan_account_call(params: dict[str, str]) -> str:
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        raise ChainFetchError("ETHERSCAN_API_KEY is required for ETH and ERC-20 balances")
    params = {**params, "chainid": "1", "apikey": api_key}
    payload = _get_json(ETHERSCAN_URL, params=params)
    status = str(payload.get("status", ""))
    message = str(payload.get("message", ""))
    result = payload.get("result")
    if status != "1" and message.upper() != "OK":
        raise ChainFetchError(f"Etherscan returned {message}: {result}")
    if result is None:
        raise ChainFetchError("Etherscan response did not include result")
    return str(result)


def _get_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    cache: ResponseCache = DEFAULT_CACHE,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    text = _get_text(url, params=params, cache=cache, ttl_seconds=ttl_seconds)
    return json.loads(text)


def _get_text(
    url: str,
    *,
    params: dict[str, str] | None = None,
    cache: ResponseCache = DEFAULT_CACHE,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    request = requests.Request("GET", url, params=params)
    prepared = _SESSION.prepare_request(request)
    if prepared.url is None:
        raise ChainFetchError(f"Could not prepare request URL for {url}")

    cache_key = _cache_key(prepared.url)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    response = _request_with_retry(prepared.url)
    cache.set(cache_key, response, ttl_seconds)
    return response


def _cache_key(url: str) -> str:
    return f"GET:{sha256(url.encode('utf-8')).hexdigest()}"


@retry(
    retry=retry_if_exception_type((requests.RequestException, RetryableHTTPError)),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _request_with_retry(url: str) -> str:
    _respect_rate_limit()
    response = _SESSION.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableHTTPError(f"HTTP {response.status_code} from {url}")
    response.raise_for_status()
    return response.text


def _respect_rate_limit() -> None:
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_REQUEST_AT
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        _LAST_REQUEST_AT = time.monotonic()
