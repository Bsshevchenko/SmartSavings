import asyncio
from aiogram import Bot, Dispatcher
from app.config import settings
from app.db import init_db
from app.routers.entries import r as entries_router


async def main() -> None:
    """Entry point: DB init, bot startup, routers wiring."""
    await init_db()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем роутеры в нужном порядке
    dp.include_router(router=entries_router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
