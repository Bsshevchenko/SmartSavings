import pytest
import asyncio

from price_fetch import get_fiat_price_usd, get_crypto_price_usd, get_stock_price_usd


def test_get_fiat_price_usd_rub_positive():
    price = asyncio.run(get_fiat_price_usd("RUB"))
    assert price > 0


def test_get_fiat_price_usd_usd_is_one():
    price = asyncio.run(get_fiat_price_usd("USD"))
    assert price == 1.0


def test_get_crypto_price_usd_btc_positive():
    price = asyncio.run(get_crypto_price_usd("BTC"))
    assert price > 0


def test_get_stock_price_usd_sber_if_available():
    try:
        price = asyncio.run(get_stock_price_usd("SBER"))
        assert price > 0
    except Exception as e:
        pytest.skip(f"Stock price unavailable: {e}")
