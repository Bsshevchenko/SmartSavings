from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from app.db.models import Entry, Currency
from app.utils.rates import CurrencyConverter
from app.db import get_session

analytics_router = Router()


async def _get_total_by_mode(user_id: int, mode: str, target_currency: str, session: AsyncSession) -> float:
    """
    Возвращает общую сумму для указанного режима ('income', 'expense', 'asset') в целевой валюте (RUB/USD).
    """
    # 1. Загружаем записи пользователя с валютой
    query = (
        select(Entry)
        .where(Entry.user_id == user_id)
        .where(Entry.mode == mode)
        .options()  # можно добавить joinedload(Entry.currency) если нужно
    )
    result = await session.execute(query)
    entries: list[Entry] = result.scalars().all()

    if not entries:
        return 0.0

    # 2. Получаем мапу currency_id → currency_name
    currency_ids = list(set(e.currency_id for e in entries if e.currency_id is not None))
    currencies = {}
    if currency_ids:
        currency_query = select(Currency).where(Currency.id.in_(currency_ids))
        cur_result = await session.execute(currency_query)
        currencies = {c.id: c.code for c in cur_result.scalars().all()}

    # 3. Конвертер
    converter = CurrencyConverter()
    await converter.update_fiat_rates()
    await converter.update_crypto_rates()

    total = Decimal("0")
    for entry in entries:
        currency = currencies.get(entry.currency_id, "USD")  # fallback: USD
        try:
            converted = await converter.convert(float(entry.amount), currency, target_currency)
            total += Decimal(str(converted))
        except Exception as e:
            print(f"[ERROR] Failed to convert {entry.amount} {currency} to {target_currency}: {e}")
            continue

    return float(total)


def _register_command(mode: str, currency: str):
    command = f"/get_{mode}_{currency.lower()}"

    @analytics_router.message(F.text == command)
    async def handler(message: Message):
        session = await get_session()
        try:
            total = await _get_total_by_mode(
                user_id=message.from_user.id,
                mode=mode,
                target_currency=currency.upper(),
                session=session
            )
        finally:
            await session.close()

        formatted = f"{total:,.2f}".replace(",", " ")
        await message.answer(f"{mode.capitalize()} в {currency.upper()}: {formatted}")


# Регистрация всех команд
for mode in ["income", "expense", "asset"]:
    for cur in ["rub", "usd"]:
        _register_command(mode, cur)
