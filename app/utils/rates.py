import httpx
from typing import Literal

FIAT_API_URL_TEMPLATE = "https://open.er-api.com/v6/latest/{base}"
CRYPTO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

FiatCurrency = Literal["USD", "RUB", "EUR"]
CryptoCurrency = Literal["BTC", "ETH", "BNB", "USDT", "USDC"]

class CurrencyConverter:
    """
    Утилита для конвертации валют и криптовалют.
    Получает курсы с внешних API:
    - фиатные: https://open.er-api.com
    - криптовалюты: https://coingecko.com
    """

    def __init__(self):
        self._fiat_rates: dict[str, float] = {}
        self._crypto_rates_usd: dict[str, float] = {}

        # соответствие тикеров CoinGecko ID
        self._crypto_id_map: dict[str, str] = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "BNB": "binancecoin",
            "USDT": "tether",
            "USDC": "usd-coin",
            "SOL": "solana",
            "TRX": "tron",
        }

    async def update_fiat_rates(self, base: FiatCurrency = "USD") -> None:
        url = FIAT_API_URL_TEMPLATE.format(base=base)
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

            response.raise_for_status()
            data = response.json()
            if "rates" not in data:
                raise ValueError(f"[FIAT] Missing 'rates' in response: {data}")
            self._fiat_rates = data["rates"]

    async def update_crypto_rates(self, cryptos: list[CryptoCurrency] = None) -> None:
        cryptos = cryptos or list(self._crypto_id_map.keys())
        ids = ",".join(self._crypto_id_map[c] for c in cryptos)

        async with httpx.AsyncClient() as client:
            response = await client.get(CRYPTO_API_URL, params={
                "ids": ids,
                "vs_currencies": "usd"
            })

            if response.status_code == 429:
                raise RuntimeError("CoinGecko rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            self._crypto_rates_usd = {
                symbol: data[self._crypto_id_map[symbol]]["usd"]
                for symbol in cryptos
                if self._crypto_id_map[symbol] in data
            }

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Конвертирует сумму из одной валюты в другую.
        """

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # Кэшируем курсы
        if not self._fiat_rates:
            await self.update_fiat_rates()
        if not self._crypto_rates_usd:
            await self.update_crypto_rates()

        def get_usd_rate(cur: str) -> float:
            cur = cur.upper()
            if cur in self._crypto_rates_usd:
                return self._crypto_rates_usd[cur]
            elif cur in self._fiat_rates:
                return 1 / self._fiat_rates[cur]
            elif cur == "USD":
                return 1.0
            else:
                raise ValueError(f"Unsupported currency: {cur}")

        # 1. Сначала в USD
        amount_in_usd = amount * get_usd_rate(from_currency)

        # 2. Теперь из USD в нужную валюту
        if to_currency == "USD":
            return amount_in_usd
        elif to_currency in self._fiat_rates:
            result = amount_in_usd * self._fiat_rates[to_currency]
            return result
        elif to_currency in self._crypto_rates_usd:
            result = amount_in_usd / self._crypto_rates_usd[to_currency]
            return result
        else:
            raise ValueError(f"Unsupported target currency: {to_currency}")
