from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime

from app.db import get_session
from app.utils.reports import report_for_expense
from app.utils.date_ranges import get_today_range, get_this_week_range, get_this_month_range
from app.repo.entry_fetcher import EntryFetcher


expenses_router = Router()


async def _send_expense_report(message: Message, label: str, date_range: tuple[datetime, datetime]):
    """
    Отправляет пользователю отчёт о расходах за указанный период.

    :param message: Объект Telegram-сообщения.
    :param label: Текстовый лейбл (например, "Расходы за сегодня").
    :param date_range: Диапазон дат (start, end).
    """
    user_id = message.from_user.id
    session = await get_session()

    fetcher = EntryFetcher(session, user_id)

    # 1. Загружаем данные
    entries, currency_map = await fetcher.fetch_entries(date_range, mode="expense")

    if not entries:
        await message.answer(f"📊 {label}: у вас не было расходов.")
        return

    # 2. Считаем конвертированные итоги
    totals = await fetcher.calculate_converted_totals(entries, currency_map)

    # 3. Формируем и отправляем отчёт
    text = report_for_expense(label, totals)
    await message.answer(text)


@expenses_router.message(F.text == "/expenses_today")
async def handle_expenses_today(message: Message):
    await _send_expense_report(message, "Расходы за сегодня", get_today_range())


@expenses_router.message(F.text == "/expenses_week")
async def handle_expenses_this_week(message: Message):
    await _send_expense_report(message, "Расходы за текущую неделю", get_this_week_range())


@expenses_router.message(F.text == "/expenses_month")
async def handle_expenses_month(message: Message):
    await _send_expense_report(message, "Расходы за текущий месяц", get_this_month_range())
