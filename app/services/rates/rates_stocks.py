import logging
from datetime import datetime, timedelta
from typing import Iterable
import httpx

MOEX_STOCK_API_TEMPLATE = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json"
)

_cache = {"data": {}, "timestamp": None}
_CACHE_TTL = timedelta(minutes=10)


class StockRatesClient:
    def __init__(self, supported: Iterable[str] | None = None):
        self._rates_usd: dict[str, float] = {}
        # supported оставлен для обратной совместимости, но не используется как фильтр
        self._supported = set(s.upper() for s in (supported or set()))

    @property
    def rates_usd(self) -> dict[str, float]:
        return self._rates_usd

    @property
    def supported(self) -> set[str]:
        return self._supported

    async def update(self, rub_per_usd: float, tickers: list[str] | None = None) -> None:
        if (
            _cache["timestamp"]
            and datetime.now() - _cache["timestamp"] < _CACHE_TTL
            and _cache["data"]
        ):
            self._rates_usd = _cache["data"]
            return

        try:
            result: dict[str, float] = {}
            # Требуем явный список тикеров; если не передан — ничего не делаем
            tickers = [t.upper() for t in (tickers or [])]

            async with httpx.AsyncClient(timeout=10.0) as client:
                for ticker in tickers:
                    url = MOEX_STOCK_API_TEMPLATE.format(ticker=ticker)
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()

                    marketdata = data.get("marketdata", {})
                    columns = marketdata.get("columns", [])
                    rows = marketdata.get("data", [])
                    try:
                        idx_last = columns.index("LAST") if "LAST" in columns else None
                        idx_secid = columns.index("SECID") if "SECID" in columns else None
                    except ValueError:
                        idx_last = idx_secid = None

                    last_price_rub: float | None = None
                    for row in rows:
                        if idx_secid is not None and row[idx_secid] and str(row[idx_secid]).upper() != ticker:
                            continue
                        if idx_last is not None and row[idx_last] is not None:
                            last_price_rub = float(row[idx_last])
                            break

                    if last_price_rub is None:
                        continue

                    # Convert RUB -> USD using rub_per_usd (RUB per 1 USD)
                    price_usd = last_price_rub / rub_per_usd
                    result[ticker] = price_usd

            if result:
                self._rates_usd = result
                _cache["data"] = self._rates_usd
                _cache["timestamp"] = datetime.now()
        except Exception:
            if _cache["data"]:
                self._rates_usd = _cache["data"]
                logging.warning("[STOCK] API error, using cached rates")
            else:
                self._rates_usd = {}
                logging.exception("[STOCK] API error, no rates available")
