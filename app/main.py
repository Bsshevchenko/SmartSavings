import asyncio
from aiogram import Bot, Dispatcher

from app.db import init_db
from app.config import settings
from app.routers.entries import r as entries_router


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

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
