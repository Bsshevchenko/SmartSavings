import logging
from datetime import datetime, timedelta
import httpx

FIAT_API_URL_TEMPLATE = "https://open.er-api.com/v6/latest/{base}"

_cache = {"data": {}, "timestamp": None}
_CACHE_TTL = timedelta(minutes=10)

FALLBACK_RATES_FIAT = {
    "RUB": 0.012,
    "EUR": 1.1,
}


class FiatRatesClient:
    def __init__(self):
        self._rates: dict[str, float] = {}

    @property
    def rates(self) -> dict[str, float]:
        return self._rates

    async def update(self, base: str = "USD") -> None:
        if (
            _cache["timestamp"]
            and datetime.now() - _cache["timestamp"] < _CACHE_TTL
            and _cache["data"]
        ):
            self._rates = _cache["data"]
            return

        try:
            url = FIAT_API_URL_TEMPLATE.format(base=base)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if "rates" not in data:
                    raise ValueError("[FIAT] Missing 'rates' in response")
                self._rates = data["rates"]
                _cache["data"] = self._rates
                _cache["timestamp"] = datetime.now()
        except Exception as e:
            if _cache["data"]:
                self._rates = _cache["data"]
                logging.warning(f"[FIAT] API error, using cached rates: {e}")
            else:
                self._rates = FALLBACK_RATES_FIAT
                logging.exception("[FIAT] API error, using fallback rates")
