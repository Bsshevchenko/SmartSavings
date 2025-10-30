import logging
from datetime import datetime, timedelta
from typing import Iterable
import httpx

MOEX_STOCK_API_TEMPLATE = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json"
)
MOEX_STOCK_API_BOARD_TEMPLATE = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities/{ticker}.json"
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
        # Требуем явный список тикеров; если не передан — ничего не делаем
        requested = [t.upper() for t in (tickers or [])]

        # Если кэш свежий и содержит все запрошенные тикеры, используем его
        if (
            _cache["timestamp"]
            and datetime.now() - _cache["timestamp"] < _CACHE_TTL
            and _cache["data"]
        ):
            cached: dict[str, float] = _cache["data"]
            if all(t in cached for t in requested):
                self._rates_usd = cached
                return

        try:
            # Начинаем с кэша (если есть), чтобы не терять ранее загруженные тикеры
            result: dict[str, float] = dict(_cache["data"]) if _cache["data"] else {}

            async with httpx.AsyncClient(timeout=10.0) as client:
                for ticker in requested:
                    last_price_rub: float | None = None

                    # Попробуем сначала по основной доске TQBR, затем общий эндпоинт
                    # Попробуем несколько популярных досок торгов + общий эндпоинт
                    boards = ["TQBR", "FQBR", "TQTF", "TQIF", "TQPI", "SMAL", "TQNE"]
                    urls_to_try = [
                        *(MOEX_STOCK_API_BOARD_TEMPLATE.format(board=b, ticker=ticker) for b in boards),
                        MOEX_STOCK_API_TEMPLATE.format(ticker=ticker),
                    ]

                    for url in urls_to_try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()

                        marketdata = data.get("marketdata", {})
                        columns = marketdata.get("columns", [])
                        rows = marketdata.get("data", [])

                        # Ищем одно из возможных полей цены
                        price_columns_priority = [
                            "LAST",           # последняя сделка
                            "LCURRENTPRICE",  # текущая расчетная цена
                            "MARKETPRICE",    # рыночная цена
                            "PREVPRICE",      # цена закрытия предыдущей сессии
                            "OPEN",           # цена открытия
                        ]
                        try:
                            idx_secid = columns.index("SECID") if "SECID" in columns else None
                        except ValueError:
                            idx_secid = None

                        idx_price_list = []
                        for col in price_columns_priority:
                            if col in columns:
                                try:
                                    idx_price_list.append((col, columns.index(col)))
                                except ValueError:
                                    pass

                        for row in rows:
                            if idx_secid is not None and row[idx_secid] and str(row[idx_secid]).upper() != ticker:
                                continue
                            for _, idx_price in idx_price_list:
                                val = row[idx_price]
                                if val is not None:
                                    last_price_rub = float(val)
                                    break
                            if last_price_rub is not None:
                                break
                        if last_price_rub is not None:
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
