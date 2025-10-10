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
    
    async with await get_session() as session:
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


@expenses_router.message(F.text == "/debug_test")
async def debug_test(message: Message):
    """Отладочная команда для проверки работы системы."""
    user_id = message.from_user.id
    
    async with await get_session() as session:
        from sqlalchemy import text
        
        # Проверяем подключение к БД
        try:
            # Проверяем общее количество записей в БД
            result = await session.execute(text("SELECT COUNT(*) FROM entries"))
            total_all_entries = result.scalar()
            
            # Проверяем записи конкретного пользователя
            result = await session.execute(text("SELECT COUNT(*) FROM entries WHERE user_id = :user_id"), {"user_id": user_id})
            total_entries = result.scalar()
            
            result = await session.execute(text("SELECT COUNT(*) FROM entries WHERE user_id = :user_id AND mode = 'expense'"), {"user_id": user_id})
            expense_entries = result.scalar()
            
            result = await session.execute(text("SELECT COUNT(*) FROM entries WHERE user_id = :user_id AND mode = 'asset'"), {"user_id": user_id})
            asset_entries = result.scalar()
            
            # Проверяем все user_id в БД
            result = await session.execute(text("SELECT DISTINCT user_id FROM entries LIMIT 5"))
            all_user_ids = [row[0] for row in result.fetchall()]
            
            await message.answer(
                f"🔍 Отладка для пользователя {user_id}:\n"
                f"• Всего записей в БД: {total_all_entries}\n"
                f"• Записей у пользователя: {total_entries}\n"
                f"• Расходов: {expense_entries}\n"
                f"• Активов: {asset_entries}\n"
                f"• User ID в БД: {all_user_ids}"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка отладки: {str(e)}")


@expenses_router.message(F.text == "/debug_crypto")
async def debug_crypto(message: Message):
    """Отладочная команда для проверки конвертации криптовалют."""
    user_id = message.from_user.id
    
    async with await get_session() as session:
        from app.services.capital_analytics import CapitalAnalyticsService
        from app.utils.rates import CurrencyConverter
        
        try:
            # Получаем последние значения активов
            result = await session.execute(text("SELECT currency_code, amount FROM asset_latest_values WHERE user_id = :user_id"), {"user_id": user_id})
            assets = result.fetchall()
            
            converter = CurrencyConverter()
            await converter.update_fiat_rates()
            await converter.update_crypto_rates()
            
            total_usd = 0
            details = []
            
            for currency_code, amount in assets:
                try:
                    converted = await converter.convert(float(amount), currency_code, "USD")
                    total_usd += converted
                    details.append(f"• {currency_code}: {amount} = ${converted:.2f}")
                except Exception as e:
                    details.append(f"• {currency_code}: {amount} = ОШИБКА: {str(e)}")
            
            await message.answer(
                f"🔍 Конвертация криптовалют для пользователя {user_id}:\n\n" +
                "\n".join(details) + 
                f"\n\n💰 Общий капитал: ${total_usd:.2f}"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка отладки крипто: {str(e)}")


@expenses_router.message(F.text == "/debug_new_capital")
async def debug_new_capital(message: Message):
    """Отладочная команда для проверки нового расчёта капитала."""
    user_id = message.from_user.id
    
    async with await get_session() as session:
        from app.services.capital_analytics import CapitalAnalyticsService
        
        try:
            analytics_service = CapitalAnalyticsService(session)
            
            # Получаем капитал в USD и RUB
            capital_usd = await analytics_service.get_current_capital(user_id, "USD")
            capital_rub = await analytics_service.get_current_capital(user_id, "RUB")
            
            # Получаем детали по активам
            result = await session.execute(text("""
                SELECT currency_code, category_name, amount 
                FROM asset_latest_values 
                WHERE user_id = :user_id
                ORDER BY currency_code, category_name
            """), {"user_id": user_id})
            
            assets = result.fetchall()
            
            details = []
            for currency_code, category_name, amount in assets:
                details.append(f"• {currency_code} {category_name}: {amount}")
            
            await message.answer(
                f"💰 Новый расчёт капитала для пользователя {user_id}:\n\n" +
                f"📊 Общий капитал:\n" +
                f"• USD: ${capital_usd:,.2f}\n" +
                f"• RUB: {capital_rub:,.0f}₽\n\n" +
                f"📋 Детали активов:\n" +
                "\n".join(details)
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка отладки капитала: {str(e)}")


@expenses_router.message(F.text == "/debug_grow")
async def debug_grow(message: Message):
    """Отладочная команда для проверки роста капитала."""
    user_id = message.from_user.id
    
    async with await get_session() as session:
        from app.services.capital_analytics import CapitalAnalyticsService
        from datetime import datetime, timedelta, timezone
        
        try:
            analytics_service = CapitalAnalyticsService(session)
            
            now = datetime.now(timezone.utc)
            current_capital_usd = await analytics_service.get_current_capital(user_id, "USD")
            current_capital_rub = await analytics_service.get_current_capital(user_id, "RUB")
            
            # Проверяем последний день предыдущего месяца
            prev_month_last_day = now.replace(day=1) - timedelta(days=1)
            
            prev_capital_usd = await analytics_service.get_capital_for_date(user_id, prev_month_last_day.date(), "USD")
            prev_capital_rub = await analytics_service.get_capital_for_date(user_id, prev_month_last_day.date(), "RUB")
            
            # Проверяем, есть ли снэпшоты
            result = await session.execute(text("""
                SELECT COUNT(*) FROM capital_snapshots WHERE user_id = :user_id
            """), {"user_id": user_id})
            snapshots_count = result.scalar()
            
            # Проверяем, есть ли данные за прошлый месяц в entries
            prev_month_start = prev_month_last_day.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev_month_end = prev_month_start.replace(month=prev_month_start.month + 1) if prev_month_start.month < 12 else prev_month_start.replace(year=prev_month_start.year + 1, month=1)
            
            result = await session.execute(text("""
                SELECT COUNT(*) FROM entries 
                WHERE user_id = :user_id AND mode = 'asset' 
                AND created_at >= :start AND created_at < :end
            """), {
                "user_id": user_id,
                "start": prev_month_start,
                "end": prev_month_end
            })
            entries_in_prev_month = result.scalar()
            
            await message.answer(
                f"🔍 Отладка роста капитала для пользователя {user_id}:\n\n" +
                f"📊 Текущий капитал (октябрь 2025):\n" +
                f"• USD: ${current_capital_usd:,.2f}\n" +
                f"• RUB: {current_capital_rub:,.0f}₽\n\n" +
                f"📅 Капитал на {prev_month_last_day.date()} (конец сентября):\n" +
                f"• USD: ${prev_capital_usd:,.2f}\n" +
                f"• RUB: {prev_capital_rub:,.0f}₽\n\n" +
                f"📸 Снэпшотов в БД: {snapshots_count}\n" +
                f"📝 Записей активов в сентябре: {entries_in_prev_month}\n\n" +
                f"📈 Рост USD: ${current_capital_usd - prev_capital_usd:,.2f}\n" +
                f"📈 Рост RUB: {current_capital_rub - prev_capital_rub:,.0f}₽"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка отладки роста: {str(e)}")


@expenses_router.message(F.text == "/reset_rates_cache")
async def reset_rates_cache(message: Message):
    """Сбрасывает кэш курсов валют."""
    try:
        from app.utils.rates import _rates_cache
        _rates_cache["fiat"]["timestamp"] = None
        _rates_cache["crypto"]["timestamp"] = None
        _rates_cache["fiat"]["data"] = {}
        _rates_cache["crypto"]["data"] = {}
        
        await message.answer("✅ Кэш курсов валют сброшен. Следующие запросы будут загружать свежие курсы.")
    except Exception as e:
        await message.answer(f"❌ Ошибка сброса кэша: {str(e)}")


@expenses_router.message(F.text == "/debug_assets")
async def debug_assets(message: Message):
    """Отладочная команда для проверки активов в БД."""
    user_id = message.from_user.id
    
    async with await get_session() as session:
        try:
            # Проверяем записи в entries
            result = await session.execute(text("""
                SELECT e.id, c.code, cat.name, e.amount, e.created_at
                FROM entries e
                LEFT JOIN currencies c ON e.currency_id = c.id
                LEFT JOIN categories cat ON e.category_id = cat.id
                WHERE e.user_id = :user_id AND e.mode = 'asset'
                ORDER BY e.created_at DESC
                LIMIT 10
            """), {"user_id": user_id})
            
            entries = result.fetchall()
            
            # Проверяем записи в asset_latest_values
            result = await session.execute(text("""
                SELECT currency_code, category_name, amount, last_updated
                FROM asset_latest_values
                WHERE user_id = :user_id
                ORDER BY currency_code, category_name
            """), {"user_id": user_id})
            
            latest_assets = result.fetchall()
            
            entries_text = "\n".join([
                f"• ID {entry[0]}: {entry[1]} {entry[2]} = {entry[3]} ({entry[4]})"
                for entry in entries
            ])
            
            latest_text = "\n".join([
                f"• {asset[0]} {asset[1]}: {asset[2]} ({asset[3]})"
                for asset in latest_assets
            ])
            
            await message.answer(
                f"🔍 Отладка активов для пользователя {user_id}:\n\n" +
                f"📝 Последние записи в entries:\n{entries_text}\n\n" +
                f"📊 Записи в asset_latest_values:\n{latest_text}"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка отладки активов: {str(e)}")
