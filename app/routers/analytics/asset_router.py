from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime, timedelta, timezone

from app.db import get_session
from app.repo.entry_fetcher import EntryFetcher
from app.utils.date_ranges import get_month_range
from app.utils.reports import report_for_assets
from app.utils.formatting import format_ru_month_label, fmt_money_str

asset_router = Router()


@asset_router.message(F.text == "/get_asset")
async def get_asset(message: Message):
    """Обработчик команды /get_asset: выводит капитал за месяц."""

    user_id = message.from_user.id
    session = await get_session()
    fetcher = EntryFetcher(session, user_id)

    now = datetime.now(timezone.utc)

    # 1. Пробуем получить активы за текущий месяц
    current_month_range = get_month_range(now)
    entries, currency_map = await fetcher.fetch_entries(current_month_range, mode="asset")

    # 2. Если записей нет → берем предыдущий месяц
    if not entries:
        prev_month_date = (now.replace(day=1) - timedelta(days=1))  # последний день прошлого месяца
        prev_month_range = get_month_range(prev_month_date)
        entries, currency_map = await fetcher.fetch_entries(prev_month_range, mode="asset")
        month_label = format_ru_month_label(prev_month_date)
    else:
        month_label = format_ru_month_label(now)

    if not entries:
        await message.answer("📊 У вас нет записей об активах за последние месяцы.")
        return

    # 3. Считаем итоги с конвертацией
    totals = await fetcher.calculate_converted_totals(entries, currency_map, targets=["RUB", "USD"])

    # 4. Формируем и отправляем отчёт
    await message.answer(report_for_assets(label=month_label, totals=totals))


@asset_router.message(F.text == "/grow_asset")
async def grow_asset(message: Message):
    """Обработчик команды /grow_asset: выводит рост капитала по сравнению с предыдущим месяцем."""

    user_id = message.from_user.id
    session = await get_session()
    fetcher = EntryFetcher(session, user_id)

    now = datetime.now(timezone.utc)

    # Текущий месяц
    current_range = get_month_range(now)
    current_entries, current_currency_map = await fetcher.fetch_entries(current_range, mode="asset")
    current_totals = await fetcher.calculate_converted_totals(current_entries, current_currency_map, targets=["RUB", "USD"]) if current_entries else {}

    # Предыдущий месяц
    prev_month_date = (now.replace(day=1) - timedelta(days=1))
    prev_range = get_month_range(prev_month_date)
    prev_entries, prev_currency_map = await fetcher.fetch_entries(prev_range, mode="asset")
    prev_totals = await fetcher.calculate_converted_totals(prev_entries, prev_currency_map, targets=["RUB", "USD"]) if prev_entries else {}

    # Если данных нет совсем
    if not current_entries and not prev_entries:
        await message.answer("📊 У вас нет записей об активах за последние месяцы.")
        return

    # Если есть только предыдущий месяц
    if not current_entries and prev_entries:
        await message.answer(
            f"📊 Данных за {format_ru_month_label(now)} нет.\n"
            f"Капитал за {format_ru_month_label(prev_month_date)}:\n"
            f"• 🇷🇺 {fmt_money_str(str(prev_totals.get('RUB', 0)))} RUB\n"
            f"• 🇺🇸 {fmt_money_str(str(prev_totals.get('USD', 0)))} USD"
        )
        return

    # Если есть только текущий месяц
    if current_entries and not prev_entries:
        await message.answer(
            f"📊 Данных за {format_ru_month_label(prev_month_date)} нет.\n"
            f"Капитал за {format_ru_month_label(now)}:\n"
            f"• 🇷🇺 {fmt_money_str(str(current_totals.get('RUB', 0)))} RUB\n"
            f"• 🇺🇸 {fmt_money_str(str(current_totals.get('USD', 0)))} USD"
        )
        return

    # Есть оба месяца → считаем рост
    rub_growth = current_totals["RUB"] - prev_totals["RUB"]
    usd_growth = current_totals["USD"] - prev_totals["USD"]

    text = "\n".join([
        f"📈 Рост капитала ({format_ru_month_label(prev_month_date)} → {format_ru_month_label(now)}):",
        f"• 🇷🇺 {fmt_money_str(str(rub_growth))} RUB "
        f"(было {fmt_money_str(str(prev_totals['RUB']))}, стало {fmt_money_str(str(current_totals['RUB']))})",
        f"• 🇺🇸 {fmt_money_str(str(usd_growth))} USD "
        f"(было {fmt_money_str(str(prev_totals['USD']))}, стало {fmt_money_str(str(current_totals['USD']))})",
    ])
    await message.answer(text)
