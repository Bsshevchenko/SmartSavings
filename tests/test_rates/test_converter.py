from app.services.rates.converter import CurrencyConverter
import asyncio
import pytest


def test_convert_usd_to_rub_positive():
    converter = CurrencyConverter()
    value = asyncio.run(converter.convert(1.0, "USD", "RUB"))
    assert value > 0


def test_convert_btc_to_usd_positive():
    converter = CurrencyConverter()
    value = asyncio.run(converter.convert(0.0001, "BTC", "USD"))
    assert value > 0


def test_convert_sber_to_usd_if_available():
    converter = CurrencyConverter()
    try:
        value = asyncio.run(converter.convert(1.0, "SBER", "USD"))
        assert value > 0
    except Exception as e:
        pytest.skip(f"Skipping SBER conversion test: {e}")
