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


async def create_monthly_snapshots():
    """
    Создаёт снэпшоты капитала для всех пользователей с активами.
    Вызывается 15-го числа каждого месяца.
    """
    session = None
    try:
        session = await get_session()
        
        # Импортируем сервис аналитики капитала
        from app.services.capital_analytics import CapitalAnalyticsService
        from app.db.models import AssetLatestValues
        from sqlalchemy import select
        
        # Получаем всех пользователей с активами
        users_result = await session.execute(
            select(AssetLatestValues.user_id).distinct()
        )
        user_ids = [row[0] for row in users_result.fetchall()]
        
        if not user_ids:
            print("[INFO] No users with assets found for monthly snapshots")
            return
        
        analytics_service = CapitalAnalyticsService(session)
        created_count = 0
        
        for user_id in user_ids:
            try:
                # Создаём снэпшот на сегодняшнюю дату
                success = await analytics_service.create_monthly_snapshot(user_id)
                if success:
                    created_count += 1
                    print(f"[INFO] Created monthly snapshot for user {user_id}")
                else:
                    print(f"[WARNING] Failed to create snapshot for user {user_id}")
            except Exception as e:
                print(f"[ERROR] Failed to create snapshot for user {user_id}: {e}")
        
        print(f"[INFO] Monthly snapshots completed: {created_count}/{len(user_ids)} users")
        
    except Exception as e:
        print(f"[ERROR] Monthly snapshots task failed: {e}")
    finally:
        if session:
            await session.close()


def schedule_monthly_snapshots():
    """
    Планирует автоматическое создание снэпшотов капитала 15-го числа каждого месяца в 10:00.
    """
    @aiocron.crontab('0 10 15 * *')  # 15-го числа каждого месяца в 10:00
    async def monthly_snapshots_task():
        await create_monthly_snapshots()
    
    print("[INFO] Monthly snapshots scheduled for 15th of each month at 10:00")
