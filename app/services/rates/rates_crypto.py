import logging
from datetime import datetime, timedelta
import httpx

CRYPTO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

_cache = {"data": {}, "timestamp": None}
_CACHE_TTL = timedelta(minutes=10)

FALLBACK_RATES_CRYPTO_USD = {
    "BTC": 120000.0,
    "ETH": 4300.0,
    "SOL": 220.0,
    "TRX": 0.34,
    "USDT": 1.0,
    "USDC": 1.0,
    "BNB": 300.0,
}


class CryptoRatesClient:
    def __init__(self):
        self._rates_usd: dict[str, float] = {}
        self._coingecko_id: dict[str, str] = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "BNB": "binancecoin",
            "USDT": "tether",
            "USDC": "usd-coin",
            "SOL": "solana",
            "TRX": "tron",
        }

    @property
    def rates_usd(self) -> dict[str, float]:
        return self._rates_usd

    async def update(self, symbols: list[str] | None = None) -> None:
        if (
            _cache["timestamp"]
            and datetime.now() - _cache["timestamp"] < _CACHE_TTL
            and _cache["data"]
        ):
            self._rates_usd = _cache["data"]
            return

        try:
            symbols = symbols or list(self._coingecko_id.keys())
            ids = ",".join(self._coingecko_id[s] for s in symbols)

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(CRYPTO_API_URL, params={
                    "ids": ids,
                    "vs_currencies": "usd",
                })

                if resp.status_code == 429 and _cache["data"]:
                    self._rates_usd = _cache["data"]
                    return

                resp.raise_for_status()
                data = resp.json()

                self._rates_usd = {
                    symbol: data[self._coingecko_id[symbol]]["usd"]
                    for symbol in symbols
                    if self._coingecko_id[symbol] in data
                }

                _cache["data"] = self._rates_usd
                _cache["timestamp"] = datetime.now()
        except Exception as e:
            if _cache["data"]:
                self._rates_usd = _cache["data"]
                logging.warning(f"[CRYPTO] API error, using cached rates: {e}")
            else:
                self._rates_usd = FALLBACK_RATES_CRYPTO_USD
                logging.exception("[CRYPTO] API error, using fallback rates")
