from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import logging

from app.db.models import User, Entry, Currency
from app.services.rates.converter import CurrencyConverter


async def get_last_week_range() -> tuple[datetime, datetime]:
    """
    Возвращает временной диапазон последних 7 дней от текущего момента (UTC).
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now
    return start, end


async def get_weekly_expenses(session, user_id: int) -> list[Entry]:
    """
    Возвращает все расходы пользователя за прошлую неделю.
    """
    start, end = await get_last_week_range()
    result = await session.execute(
        select(Entry)
        .where(Entry.user_id == user_id)
        .where(Entry.mode == "expense")
        .where(Entry.created_at.between(start, end))
    )
    return result.scalars().all()


async def build_report(user_id: int, session) -> str:
    entries = await get_weekly_expenses(session, user_id)
    if not entries:
        return "📊 За прошлую неделю у вас не было расходов."

    currency_ids = list(set(e.currency_id for e in entries if e.currency_id))
    currency_map = {}
    if currency_ids:
        result = await session.execute(select(Currency).where(Currency.id.in_(currency_ids)))
        currency_map = {c.id: c.code for c in result.scalars().all()}

    converter = CurrencyConverter()
    await converter.update_fiat_rates()
    await converter.update_crypto_rates()

    totals = {"RUB": 0, "USD": 0, "VND": 0}
    for entry in entries:
        currency = currency_map.get(entry.currency_id, "USD")
        for target in totals:
            try:
                converted = await converter.convert(float(entry.amount), currency, target)
                totals[target] += converted
            except Exception:
                logging.exception(f"Failed to convert {entry.amount} {currency} to {target}")
                continue

    return "\n".join([
        "📅 Расходы за прошлую неделю:",
        f"• 🇷🇺 {totals['RUB']:.2f} RUB",
        f"• 🇺🇸 {totals['USD']:.2f} USD",
        f"• 🇻🇳 {totals['VND']:.2f} VND"
    ])
