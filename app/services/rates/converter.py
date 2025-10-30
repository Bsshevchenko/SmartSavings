import logging
from typing import Literal

from app.services.rates.rates_fiat import FiatRatesClient
from app.services.rates.rates_crypto import CryptoRatesClient
from app.services.rates.rates_stocks import StockRatesClient

FiatCurrency = Literal["USD", "RUB", "EUR"]
CryptoCurrency = Literal["BTC", "ETH", "BNB", "USDT", "USDC"]


class CurrencyConverter:
    """
    Оркестратор конвертации между фиатом, криптой и акциями.
    """

    def __init__(self):
        self._fiat_rates: dict[str, float] = {}
        self._crypto_rates_usd: dict[str, float] = {}
        self._stock_rates_usd: dict[str, float] = {}

        self._fiat_client = FiatRatesClient()
        self._crypto_client = CryptoRatesClient()
        self._stock_client = StockRatesClient()

        self._moex_supported: set[str] = set(self._stock_client.supported)

    async def update_fiat_rates(self, base: FiatCurrency = "USD") -> None:
        await self._fiat_client.update(base)
        self._fiat_rates = dict(self._fiat_client.rates)

    async def update_crypto_rates(self, cryptos: list[CryptoCurrency] = None) -> None:
        await self._crypto_client.update(cryptos)
        self._crypto_rates_usd = dict(self._crypto_client.rates_usd)

    async def update_stock_rates(self, tickers: list[str] | None = None) -> None:
        if not self._fiat_rates:
            await self.update_fiat_rates()
        rub_per_usd = self._fiat_rates.get("RUB")
        if not rub_per_usd:
            raise RuntimeError("RUB rate is missing for stock conversion")
        await self._stock_client.update(rub_per_usd, tickers)
        self._stock_rates_usd = dict(self._stock_client.rates_usd)

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if not self._fiat_rates:
            await self.update_fiat_rates()
        if not self._crypto_rates_usd:
            await self.update_crypto_rates()
        def is_potential_stock(sym: str) -> bool:
            if sym == "USD" or sym in self._fiat_rates or sym in self._crypto_rates_usd:
                return False
            # Эвристика: латинские буквы/цифры, длина 1..8 — подходяще для SECID
            return sym.isalnum() and sym.upper() == sym and 1 <= len(sym) <= 8

        requested_stock_tickers: list[str] = []
        if is_potential_stock(from_currency):
            requested_stock_tickers.append(from_currency)
        if is_potential_stock(to_currency) and to_currency != from_currency:
            requested_stock_tickers.append(to_currency)

        if requested_stock_tickers:
            await self.update_stock_rates(requested_stock_tickers)

        def get_usd_rate(cur: str) -> float:
            cur = cur.upper()
            if cur in self._crypto_rates_usd:
                return self._crypto_rates_usd[cur]
            elif cur in self._stock_rates_usd:
                return self._stock_rates_usd[cur]
            elif cur in self._fiat_rates:
                return 1 / self._fiat_rates[cur]
            elif cur == "USD":
                return 1.0
            else:
                raise ValueError(f"Unsupported currency: {cur}")

        amount_in_usd = amount * get_usd_rate(from_currency)

        if to_currency == "USD":
            return amount_in_usd
        elif to_currency in self._fiat_rates:
            return amount_in_usd * self._fiat_rates[to_currency]
        elif to_currency in self._crypto_rates_usd:
            return amount_in_usd / self._crypto_rates_usd[to_currency]
        elif to_currency in self._stock_rates_usd:
            return amount_in_usd / self._stock_rates_usd[to_currency]
        else:
            raise ValueError(f"Unsupported target currency: {to_currency}")
