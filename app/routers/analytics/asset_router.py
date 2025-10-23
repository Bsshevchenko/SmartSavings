from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime, timedelta, timezone

from app.db import get_session
from app.repo.entry_fetcher import EntryFetcher
from app.utils.date_ranges import get_month_range
from app.utils.reports import report_for_assets
from app.utils.formatting import format_ru_month_label, fmt_money_str, fmt_crypto_str
from app.services.capital_analytics import CapitalAnalyticsService

asset_router = Router()


@asset_router.message(F.text == "/get_asset")
async def get_asset(message: Message):
    """Обработчик команды /get_asset: выводит текущий капитал."""

    user_id = message.from_user.id
    
    async with await get_session() as session:
        try:
            # Используем новый сервис, но с fallback на старый подход
            analytics_service = CapitalAnalyticsService(session)
            
            # Получаем текущий капитал
            capital_usd = await analytics_service.get_current_capital(user_id, "USD")
            capital_rub = await analytics_service.get_current_capital(user_id, "RUB")
            
            # Если новый подход не работает, используем старый
            if capital_usd == 0 and capital_rub == 0:
                # Используем старый подход через EntryFetcher
                fetcher = EntryFetcher(session, user_id)
                now = datetime.now(timezone.utc)
                
                # Получаем активы за последние 3 месяца
                current_month_range = get_month_range(now)
                entries, currency_map = await fetcher.fetch_entries(current_month_range, mode="asset")
                
                if not entries:
                    # Пробуем предыдущий месяц
                    prev_month_date = (now.replace(day=1) - timedelta(days=1))
                    prev_month_range = get_month_range(prev_month_date)
                    entries, currency_map = await fetcher.fetch_entries(prev_month_range, mode="asset")
                    month_label = format_ru_month_label(prev_month_date)
                else:
                    month_label = format_ru_month_label(now)
                
                if not entries:
                    await message.answer("📊 У вас пока нет активов.")
                    return
                
                # Считаем итоги с конвертацией
                totals = await fetcher.calculate_converted_totals(entries, currency_map, targets=["RUB", "USD"])
                await message.answer(report_for_assets(label=f"Активы ({month_label})", totals=totals))
                return
            
            # Формируем отчёт для нового подхода
            totals = {
                "USD": capital_usd,
                "RUB": capital_rub
            }
            
            await message.answer(report_for_assets(label="Текущий капитал", totals=totals))
            
        except Exception as e:
            print(f"ERROR in get_asset: {e}")
            await message.answer(f"❌ Ошибка при расчёте капитала: {str(e)}")


@asset_router.message(F.text == "/grow_asset")
async def grow_asset(message: Message):
    """Обработчик команды /grow_asset: выводит рост капитала по сравнению с предыдущим месяцем."""

    user_id = message.from_user.id
    async with await get_session() as session:
        analytics_service = CapitalAnalyticsService(session)
        
        try:
            now = datetime.now(timezone.utc)
            
            # Текущий капитал
            current_capital_usd = await analytics_service.get_current_capital(user_id, "USD")
            current_capital_rub = await analytics_service.get_current_capital(user_id, "RUB")
            
            # Капитал на последний день прошлого месяца
            prev_month_last_day = now.replace(day=1) - timedelta(days=1)
            prev_capital_usd = await analytics_service.get_capital_for_date(user_id, prev_month_last_day.date(), "USD")
            prev_capital_rub = await analytics_service.get_capital_for_date(user_id, prev_month_last_day.date(), "RUB")
            
            # Если нет данных
            if current_capital_usd == 0 and prev_capital_usd == 0:
                await message.answer("📊 У вас пока нет активов.")
                return
            
            # Если есть только текущие данные
            if prev_capital_usd == 0:
                await message.answer(
                    f"📊 Текущий капитал:\n"
                    f"• 🇷🇺 {fmt_money_str(str(current_capital_rub))} RUB\n"
                    f"• 🇺🇸 {fmt_money_str(str(current_capital_usd))} USD\n\n"
                    f"Исторических данных для сравнения пока нет."
                )
                return
            
            # Рассчитываем рост
            rub_growth = current_capital_rub - prev_capital_rub
            usd_growth = current_capital_usd - prev_capital_usd
            
            rub_growth_percent = (rub_growth / prev_capital_rub * 100) if prev_capital_rub > 0 else 0
            usd_growth_percent = (usd_growth / prev_capital_usd * 100) if prev_capital_usd > 0 else 0
            
            # Формируем сообщение
            growth_emoji_rub = "📈" if rub_growth >= 0 else "📉"
            growth_emoji_usd = "📈" if usd_growth >= 0 else "📉"
            
            # Форматируем названия месяцев
            current_month_name = format_ru_month_label(now)
            prev_month_name = format_ru_month_label(prev_month_last_day)
            
            text = "\n".join([
                f"📊 Динамика капитала по месяцам:",
                f"",
                f"🇷🇺 RUB:",
                f"  {prev_month_name}: {fmt_money_str(str(prev_capital_rub))}",
                f"  {current_month_name}: {fmt_money_str(str(current_capital_rub))}",
                f"  {growth_emoji_rub} {fmt_money_str(str(rub_growth))} ({rub_growth_percent:+.1f}%)",
                f"",
                f"🇺🇸 USD:",
                f"  {prev_month_name}: {fmt_money_str(str(prev_capital_usd))}",
                f"  {current_month_name}: {fmt_money_str(str(current_capital_usd))}",
                f"  {growth_emoji_usd} {fmt_money_str(str(usd_growth))} ({usd_growth_percent:+.1f}%)",
            ])
            
            await message.answer(text)
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при расчёте роста капитала: {str(e)}")


@asset_router.message(F.text == "/snapshot_asset")
async def create_snapshot(message: Message):
    """Обработчик команды /snapshot_asset: создаёт снэпшот текущего капитала."""
    
    user_id = message.from_user.id
    async with await get_session() as session:
        analytics_service = CapitalAnalyticsService(session)
        
        try:
            # Создаём снэпшот на сегодняшнюю дату
            await analytics_service.create_monthly_snapshot(user_id)
            
            # Получаем текущий капитал для отчёта
            capital_usd = await analytics_service.get_current_capital(user_id, "USD")
            capital_rub = await analytics_service.get_current_capital(user_id, "RUB")
            
            text = "\n".join([
                "📸 Снэпшот капитала создан!",
                "",
                f"📊 Текущий капитал:",
                f"• 🇷🇺 {fmt_money_str(str(capital_rub))} RUB",
                f"• 🇺🇸 {fmt_money_str(str(capital_usd))} USD",
                "",
                "💡 Снэпшоты помогают корректно анализировать динамику капитала."
            ])
            
            await message.answer(text)
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании снэпшота: {str(e)}")


@asset_router.message(F.text == "/list_assets")
async def list_assets(message: Message):
    """Обработчик команды /list_assets: показывает детальный список всех активов."""
    
    user_id = message.from_user.id
    async with await get_session() as session:
        try:
            # Получаем все активы из asset_latest_values
            from sqlalchemy import select
            from app.db.models import AssetLatestValues
            
            result = await session.execute(
                select(AssetLatestValues)
                .where(AssetLatestValues.user_id == user_id)
                .order_by(AssetLatestValues.currency_code, AssetLatestValues.category_name)
            )
            assets = result.scalars().all()
            
            if not assets:
                await message.answer("📊 У вас пока нет активов.")
                return
            
            # Группируем активы по валютам
            assets_by_currency = {}
            for asset in assets:
                currency = asset.currency_code
                if currency not in assets_by_currency:
                    assets_by_currency[currency] = []
                assets_by_currency[currency].append(asset)
            
            # Формируем красивое сообщение
            text_parts = ["💼 **Детальный список активов:**\n"]
            
            total_usd = 0
            total_rub = 0
            
            # Конвертер для расчета в USD и RUB
            from app.utils.rates import CurrencyConverter
            converter = CurrencyConverter()
            await converter.update_fiat_rates()
            await converter.update_crypto_rates()
            
            for currency, currency_assets in assets_by_currency.items():
                # Название валюты жирным курсивом
                text_parts.append(f"***{currency}:***")
                
                currency_total = 0
                for asset in currency_assets:
                    amount = float(asset.amount)
                    currency_total += amount
                    
                    # Форматируем название категории без эмодзи
                    category_name = asset.category_name or "Без категории"
                    
                    # Используем специальное форматирование для криптовалют
                    if currency in ["BTC", "ETH", "SOL", "USDT", "USDC", "TRX"]:
                        formatted_amount = fmt_crypto_str(str(amount), currency)
                    else:
                        formatted_amount = fmt_money_str(str(amount))
                    text_parts.append(f"  {category_name}: {formatted_amount}")
                
                # Конвертируем в USD и RUB для общего итога
                try:
                    usd_value = await converter.convert(currency_total, currency, "USD")
                    rub_value = await converter.convert(currency_total, currency, "RUB")
                    total_usd += usd_value
                    total_rub += rub_value
                except Exception as e:
                    print(f"Ошибка конвертации {currency}: {e}")
                
                text_parts.append("")
            
            # Добавляем общие итоги
            text_parts.extend([
                "📊 **Общие итоги:**",
                f"• 🇺🇸 **USD:** {fmt_money_str(str(total_usd))}",
                f"• 🇷🇺 **RUB:** {fmt_money_str(str(total_rub))}",
                "",
                f"📅 **Обновлено:** {assets[0].last_updated.strftime('%d.%m.%Y %H:%M') if assets else 'Неизвестно'}"
            ])
            
            text = "\n".join(text_parts)
            await message.answer(text, parse_mode="Markdown")
            
        except Exception as e:
            print(f"ERROR in list_assets: {e}")
            await message.answer(f"❌ Ошибка при получении списка активов: {str(e)}")
