import asyncio
from aiogram import Bot, Dispatcher

from app.db import init_db
from app.config import settings
from app.routers.entries import r as entries_router
from app.scheduler.scheduler import schedule_report_dispatch
from app.routers.analytics.analytics_router import analytics_router
from app.routers.analytics.expenses_router import expenses_router
from app.routers.analytics.incomes_router import incomes_router
from app.services.analytics.expense.expense_reports import build_report
from app.routers.analytics.asset_router import asset_router


async def main() -> None:
    """Главная точка входа в приложение SmartSavings.

    Последовательно выполняет:
      1. Инициализацию базы данных (`init_db`).
      2. Запуск Telegram-бота с токеном из настроек.
      3. Создание и настройку диспетчера (`Dispatcher`).
      4. Подключение всех роутеров (например, `entries_router`) для обработки команд и событий.
      5. Запуск цикла обработки сообщений (`start_polling`).

    Эта функция вызывается при запуске проекта, когда скрипт
    запускается напрямую (`python main.py`).
    """
    await init_db()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем роутеры в нужном порядке
    dp.include_router(router=entries_router)
    dp.include_router(router=expenses_router)
    dp.include_router(router=incomes_router)
    dp.include_router(router=asset_router)
    schedule_report_dispatch(
        bot=bot,
        report_fn=build_report,
        cron="0 9 * * MON",  # Каждый понедельник в 09:00 по UTC
        report_name="📊 Weekly expense report"
    )
    dp.include_router(router=analytics_router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
