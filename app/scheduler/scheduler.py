import aiocron
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Callable, Awaitable

from app.db import get_session
from app.db.models import User


def schedule_report_dispatch(
    *,
    bot: Bot,
    report_fn: Callable[[int, AsyncSession], Awaitable[str]],
    cron: str,
    report_name: str = "Unnamed report"
) -> None:
    """
    Планировщик кастомной рассылки отчётов пользователям по расписанию.

    :param bot: Telegram bot instance
    :param report_fn: Функция, возвращающая текст отчёта по user_id и сессии
    :param cron: Cron-выражение (пример: '0 9 * * MON')
    :param report_name: Имя отчёта (для логов)
    """
    @aiocron.crontab(cron)
    async def cron_task():
        session = None
        try:
            session = await get_session()
            users_result = await session.execute(select(User.id))
            user_ids = [row[0] for row in users_result.fetchall()]

            for user_id in user_ids:
                try:
                    report = await report_fn(user_id, session)
                    await bot.send_message(chat_id=user_id, text=report)
                except Exception as e:
                    print(f"[ERROR] Failed to send {report_name} to user {user_id}: {e}")
        except Exception as e:
            print(f"[ERROR] Report dispatch '{report_name}' failed: {e}")
        finally:
            if session:
                await session.close()
