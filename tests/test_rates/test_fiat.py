from app.services.rates.rates_fiat import FiatRatesClient
import asyncio

def test_fiat_update_and_contains_basic_currencies():
    client = FiatRatesClient()
    asyncio.run(client.update(base="USD"))
    rates = client.rates

    assert isinstance(rates, dict)
    # Должны присутствовать ключевые валюты и быть положительными
    assert "RUB" in rates
    assert "EUR" in rates
    assert rates["RUB"] > 0
    assert rates["EUR"] > 0
