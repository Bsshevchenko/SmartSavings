from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple
import logging

from app.services.asset_service import AssetService
from app.services.rates import CurrencyConverter


async def get_growth_data(service: AssetService, user_id: int) -> Tuple[datetime, datetime, Dict[str, float], Dict[str, float]]:
    """Возвращает данные для отчёта о росте капитала: даты и капиталы."""
    now = datetime.now(timezone.utc)
    current_capital = await service.get_current_capital(user_id, ["RUB", "USD"])

    prev_month_last_day = now.replace(day=1) - timedelta(days=1)
    prev_capital = await service.get_capital_for_date(user_id, prev_month_last_day.date(), ["RUB", "USD"])

    return prev_month_last_day, now, prev_capital, current_capital


async def compute_totals_usd_rub(assets_by_currency: dict) -> Tuple[float, float, datetime | None]:
    """Считает общие итоги по всем активам в USD и RUB, возвращает также последний updated_at."""
    converter = CurrencyConverter()
    await converter.update_fiat_rates()
    await converter.update_crypto_rates()

    total_usd = 0.0
    total_rub = 0.0
    last_updated = None

    for currency, items in assets_by_currency.items():
        currency_total = 0.0
        for asset in items:
            amount = float(asset.amount)
            currency_total += amount
            if not last_updated or asset.last_updated > last_updated:
                last_updated = asset.last_updated

        try:
            usd_value = await converter.convert(currency_total, currency, "USD")
            rub_value = await converter.convert(currency_total, currency, "RUB")
            total_usd += usd_value
            total_rub += rub_value
        except Exception:
            logging.exception(f"Ошибка конвертации {currency}")

    return total_usd, total_rub, last_updated
