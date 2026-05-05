from __future__ import annotations

from decimal import Decimal

from src import chain


def test_fetch_btc_balance_converts_satoshis_to_btc(mocker) -> None:
    mocker.patch(
        "src.chain._get_json",
        return_value={
            "chain_stats": {
                "funded_txo_sum": 12_500_000_000,
                "spent_txo_sum": 2_500_000_000,
            },
            "mempool_stats": {
                "funded_txo_sum": 100_000_000,
                "spent_txo_sum": 50_000_000,
            },
        },
    )

    assert chain.fetch_btc_balance("btc-address") == Decimal("100.5")


def test_fetch_eth_balance_converts_wei_to_eth(mocker) -> None:
    mocker.patch("src.chain._etherscan_account_call", return_value="1234567890000000000")

    assert chain.fetch_eth_balance("eth-address") == Decimal("1.23456789")


def test_fetch_erc20_balance_converts_token_decimals(mocker) -> None:
    mocker.patch("src.chain._etherscan_account_call", return_value="123456789")

    assert chain.fetch_erc20_balance("token-address", "USDC") == Decimal("123.456789")


def test_cache_key_hashes_full_url_without_exposing_api_key() -> None:
    key = chain._cache_key("https://api.etherscan.io/v2/api?apikey=SECRET&address=abc")

    assert key.startswith("GET:")
    assert "SECRET" not in key
    assert "apikey" not in key.lower()
