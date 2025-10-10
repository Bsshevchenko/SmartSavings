import httpx
from typing import Literal
from datetime import datetime, timedelta

FIAT_API_URL_TEMPLATE = "https://open.er-api.com/v6/latest/{base}"
CRYPTO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

# Кэш для курсов с временными метками
_rates_cache = {
    "fiat": {"data": {}, "timestamp": None},
    "crypto": {"data": {}, "timestamp": None}
}

# Время жизни кэша (10 минут)
CACHE_DURATION = timedelta(minutes=10)

# Fallback курсы на случай недоступности API
FALLBACK_RATES = {
    "crypto": {
        "BTC": 120000.0,
        "ETH": 4300.0,
        "SOL": 220.0,
        "TRX": 0.34,
        "USDT": 1.0,
        "USDC": 1.0,
        "BNB": 300.0
    },
    "fiat": {
        "RUB": 0.012,
        "EUR": 1.1
    }
}

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
        # Проверяем кэш
        if (_rates_cache["fiat"]["timestamp"] and 
            datetime.now() - _rates_cache["fiat"]["timestamp"] < CACHE_DURATION and
            _rates_cache["fiat"]["data"]):
            self._fiat_rates = _rates_cache["fiat"]["data"]
            return
        
        try:
            url = FIAT_API_URL_TEMPLATE.format(base=base)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                if "rates" not in data:
                    raise ValueError(f"[FIAT] Missing 'rates' in response: {data}")
                self._fiat_rates = data["rates"]
                
                # Сохраняем в кэш
                _rates_cache["fiat"]["data"] = self._fiat_rates
                _rates_cache["fiat"]["timestamp"] = datetime.now()
        except Exception as e:
            # Если API недоступен, используем кэшированные данные или fallback
            if _rates_cache["fiat"]["data"]:
                self._fiat_rates = _rates_cache["fiat"]["data"]
            else:
                self._fiat_rates = FALLBACK_RATES["fiat"]
                print(f"Warning: Using fallback fiat rates due to API error: {e}")

    async def update_crypto_rates(self, cryptos: list[CryptoCurrency] = None) -> None:
        # Проверяем кэш
        if (_rates_cache["crypto"]["timestamp"] and 
            datetime.now() - _rates_cache["crypto"]["timestamp"] < CACHE_DURATION and
            _rates_cache["crypto"]["data"]):
            self._crypto_rates_usd = _rates_cache["crypto"]["data"]
            return
        
        try:
            cryptos = cryptos or list(self._crypto_id_map.keys())
            ids = ",".join(self._crypto_id_map[c] for c in cryptos)

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(CRYPTO_API_URL, params={
                    "ids": ids,
                    "vs_currencies": "usd"
                })

                if response.status_code == 429:
                    # Если превышен лимит, используем кэшированные данные
                    if _rates_cache["crypto"]["data"]:
                        self._crypto_rates_usd = _rates_cache["crypto"]["data"]
                        return
                    else:
                        raise RuntimeError("CoinGecko rate limit exceeded and no cached data available")

                response.raise_for_status()
                data = response.json()

                self._crypto_rates_usd = {
                    symbol: data[self._crypto_id_map[symbol]]["usd"]
                    for symbol in cryptos
                    if self._crypto_id_map[symbol] in data
                }
                
                # Сохраняем в кэш
                _rates_cache["crypto"]["data"] = self._crypto_rates_usd
                _rates_cache["crypto"]["timestamp"] = datetime.now()
        except Exception as e:
            # Если API недоступен, используем кэшированные данные или fallback
            if _rates_cache["crypto"]["data"]:
                self._crypto_rates_usd = _rates_cache["crypto"]["data"]
            else:
                self._crypto_rates_usd = FALLBACK_RATES["crypto"]
                print(f"Warning: Using fallback crypto rates due to API error: {e}")

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Конвертирует сумму из одной валюты в другую.
        """

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # Обновляем курсы только если их нет (кэширование уже встроено в update_*_rates)
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
