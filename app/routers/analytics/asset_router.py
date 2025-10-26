from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime, timedelta, timezone

from app.db import get_session
from app.utils.reports import report_for_assets
from app.utils.formatting import format_ru_month_label, fmt_money_str, fmt_crypto_str
from app.services.asset_service import AssetService

asset_router = Router()


@asset_router.message(F.text == "/get_asset")
async def get_asset(message: Message):
    """Обработчик команды /get_asset: выводит текущий капитал."""

    user_id = message.from_user.id
    
    async with await get_session() as session:
        try:
            service = AssetService(session)
            capital = await service.get_current_capital(user_id, ["RUB", "USD"])
            
            # Проверяем, есть ли активы
            if all(value == 0 for value in capital.values()):
                await message.answer("📊 У вас пока нет активов.")
                return
            
            await message.answer(report_for_assets(label="Текущий капитал", totals=capital))
            
        except Exception as e:
            print(f"ERROR in get_asset: {e}")
            await message.answer(f"❌ Ошибка при расчёте капитала: {str(e)}")


@asset_router.message(F.text == "/grow_asset")
async def grow_asset(message: Message):
    """Обработчик команды /grow_asset: выводит рост капитала по сравнению с предыдущим месяцем."""

    user_id = message.from_user.id
    async with await get_session() as session:
        service = AssetService(session)
        
        try:
            now = datetime.now(timezone.utc)
            
            # Текущий капитал
            current_capital = await service.get_current_capital(user_id, ["RUB", "USD"])
            
            # Капитал на последний день прошлого месяца
            prev_month_last_day = now.replace(day=1) - timedelta(days=1)
            prev_capital = await service.get_capital_for_date(user_id, prev_month_last_day.date(), ["RUB", "USD"])
            
            # Если нет данных
            if all(value == 0 for value in current_capital.values()) and all(value == 0 for value in prev_capital.values()):
                await message.answer("📊 У вас пока нет активов.")
                return
            
            # Если есть только текущие данные
            if all(value == 0 for value in prev_capital.values()):
                await message.answer(
                    f"📊 Текущий капитал:\n"
                    f"• 🇷🇺 {fmt_money_str(str(current_capital['RUB']))} RUB\n"
                    f"• 🇺🇸 {fmt_money_str(str(current_capital['USD']))} USD\n\n"
                    f"Исторических данных для сравнения пока нет."
                )
                return
            
            # Рассчитываем рост
            rub_growth = current_capital['RUB'] - prev_capital['RUB']
            usd_growth = current_capital['USD'] - prev_capital['USD']
            
            rub_growth_percent = (rub_growth / prev_capital['RUB'] * 100) if prev_capital['RUB'] > 0 else 0
            usd_growth_percent = (usd_growth / prev_capital['USD'] * 100) if prev_capital['USD'] > 0 else 0
            
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
                f"  {prev_month_name}: {fmt_money_str(str(prev_capital['RUB']))}",
                f"  {current_month_name}: {fmt_money_str(str(current_capital['RUB']))}",
                f"  {growth_emoji_rub} {fmt_money_str(str(rub_growth))} ({rub_growth_percent:+.1f}%)",
                f"",
                f"🇺🇸 USD:",
                f"  {prev_month_name}: {fmt_money_str(str(prev_capital['USD']))}",
                f"  {current_month_name}: {fmt_money_str(str(current_capital['USD']))}",
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
        service = AssetService(session)
        
        try:
            # Создаём снэпшот на сегодняшнюю дату
            success = await service.create_monthly_snapshot(user_id)
            
            if not success:
                await message.answer("📸 Снэпшот уже существует для этой даты.")
                return
            
            # Получаем текущий капитал для отчёта
            capital = await service.get_current_capital(user_id, ["RUB", "USD"])
            
            text = "\n".join([
                "📸 Снэпшот капитала создан!",
                "",
                f"📊 Текущий капитал:",
                f"• 🇷🇺 {fmt_money_str(str(capital['RUB']))} RUB",
                f"• 🇺🇸 {fmt_money_str(str(capital['USD']))} USD",
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
            service = AssetService(session)
            assets_by_currency = await service.get_detailed_assets_list(user_id)
            
            if not assets_by_currency:
                await message.answer("📊 У вас пока нет активов.")
                return
            
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
                f"📅 **Обновлено:** {currency_assets[0].last_updated.strftime('%d.%m.%Y %H:%M') if currency_assets else 'Неизвестно'}"
            ])
            
            text = "\n".join(text_parts)
            await message.answer(text, parse_mode="Markdown")
            
        except Exception as e:
            print(f"ERROR in list_assets: {e}")
            await message.answer(f"❌ Ошибка при получении списка активов: {str(e)}")
