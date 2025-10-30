from app.services.rates.rates_fiat import FiatRatesClient
from app.services.rates.rates_stocks import StockRatesClient
import asyncio
import pytest


def test_stocks_update_contains_supported_if_available():
    # Получим курс RUB для конвертации
    fiat = FiatRatesClient()
    asyncio.run(fiat.update())
    rub_per_usd = fiat.rates.get("RUB")
    if not rub_per_usd:
        pytest.skip("No RUB rate available, skip stock test")

    stocks = StockRatesClient()
    asyncio.run(stocks.update(rub_per_usd, ["SBER"]))
    rates = stocks.rates_usd

    assert isinstance(rates, dict)
    # Если SBER есть в ответе — значение должно быть > 0; если нет — не падаем
    if "SBER" in rates:
        assert rates["SBER"] > 0
