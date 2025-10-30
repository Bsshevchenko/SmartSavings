from __future__ import annotations

from app.services.rates.rates_fiat import FiatRatesClient
from app.services.rates.rates_crypto import CryptoRatesClient
from app.services.rates.rates_stocks import StockRatesClient


async def get_fiat_price_usd(symbol: str) -> float:
    """
    Возвращает цену 1 единицы фиатной валюты в USD.
    Пример: RUB -> USD per 1 RUB.
    """
    s = symbol.strip().upper()
    if s == "USD":
        return 1.0
    fiat = FiatRatesClient()
    await fiat.update()
    rates = fiat.rates  # rates[to] = to per USD
    if s not in rates:
        raise ValueError(f"Unknown fiat currency: {s}")
    rub_per_usd = rates[s]
    return 1.0 / rub_per_usd


async def get_crypto_price_usd(symbol: str) -> float:
    """
    Возвращает цену 1 единицы криптовалюты в USD.
    Пример: BTC -> USD.
    """
    s = symbol.strip().upper()
    client = CryptoRatesClient()
    await client.update([s])
    if s not in client.rates_usd:
        raise ValueError(f"Unknown crypto: {s}")
    return float(client.rates_usd[s])


async def get_stock_price_usd(symbol: str) -> float:
    """
    Возвращает цену 1 акции (MOEX SECID) в USD.
    Пример: SBER -> USD.
    """
    s = symbol.strip().upper()
    fiat = FiatRatesClient()
    await fiat.update()
    rub_per_usd = fiat.rates.get("RUB")
    if not rub_per_usd:
        raise RuntimeError("RUB rate unavailable")
    client = StockRatesClient()
    await client.update(rub_per_usd, [s])
    if s not in client.rates_usd:
        raise ValueError(f"Unknown or unavailable stock: {s}")
    return float(client.rates_usd[s])


if __name__ == "__main__":
    import asyncio
    print(asyncio.run(get_fiat_price_usd("VND")))
    print(asyncio.run(get_crypto_price_usd("BTC")))
    print(asyncio.run(get_stock_price_usd("YDEX")))
