from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime

from app.db import get_session
from app.utils.reports import report_for_income
from app.utils.date_ranges import get_this_month_range
from app.services.report_service import ReportService


incomes_router = Router()


async def _send_income_report(message: Message, label: str, date_range: tuple[datetime, datetime]):
    """
    Отправляет пользователю отчёт о доходах за указанный период.

    :param message: Объект Telegram-сообщения.
    :param label: Текстовый лейбл (например, "Доходы за текущий месяц").
    :param date_range: Диапазон дат (start, end).
    """
    user_id = message.from_user.id
    async with await get_session() as session:
        service = ReportService(session)

        # Получаем итоги за период
        totals = await service.get_period_totals(user_id, date_range, "income", ["RUB", "USD", "VND"])

        if not totals or all(value == 0 for value in totals.values()):
            await message.answer(f"💰 {label}: у вас не было доходов.")
            return

        # Формируем и отправляем отчёт
        text = report_for_income(label, totals)
        await message.answer(text)


@incomes_router.message(F.text == "/get_incomes")
async def handle_get_incomes(message: Message):
    await _send_income_report(message, "Доходы за текущий месяц", get_this_month_range())
