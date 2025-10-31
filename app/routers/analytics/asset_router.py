from aiogram import Router, F
from aiogram.types import Message
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

from app.db import get_session
from app.utils.reports import (
    report_for_assets,
    report_asset_growth,
    report_asset_snapshot_created,
    report_assets_detailed_list,
    report_asset_no_history,
)
from app.utils.formatting import fmt_money_str
from app.services.asset_service import AssetService
from app.services.analytics.asset.asset_analytics import get_growth_data, compute_totals_usd_rub

asset_router = Router()


@asset_router.message(F.text == "/get_asset")
async def get_asset(message: Message):
    """Обработчик команды /get_asset: выводит текущий капитал."""

    user_id = message.from_user.id
    
    async with await get_session() as session:
        try:
            # Принудительно синхронизируемся с БД для SQLite WAL режима
            if hasattr(session.bind, 'sync_engine') and 'sqlite' in str(session.bind.url):
                await session.execute(text("SELECT 1"))  # Принудительная синхронизация с WAL
            
            service = AssetService(session)
            capital = await service.get_current_capital(user_id, ["RUB", "USD"])
            
            # Логируем для диагностики
            logging.info(f"get_asset for user {user_id}: capital = {capital}")
            
            # Проверяем, есть ли активы
            if all(value == 0 for value in capital.values()):
                await message.answer("📊 У вас пока нет активов.")
                return
            
            await message.answer(report_for_assets(label="Текущий капитал", totals=capital))
            
        except Exception:
            logging.exception("ERROR in get_asset")
            await message.answer(f"❌ Ошибка при расчёте капитала")


@asset_router.message(F.text == "/grow_asset")
async def grow_asset(message: Message):
    """Обработчик команды /grow_asset: выводит рост капитала по сравнению с предыдущим месяцем."""

    user_id = message.from_user.id
    async with await get_session() as session:
        service = AssetService(session)
        
        try:
            prev_date, current_date, prev_capital, current_capital = await get_growth_data(service, user_id)

            if all(value == 0 for value in current_capital.values()) and all(value == 0 for value in prev_capital.values()):
                await message.answer("📊 У вас пока нет активов.")
                return

            if all(value == 0 for value in prev_capital.values()):
                await message.answer(report_asset_no_history(current_capital))
                return

            text = report_asset_growth(prev_date, current_date, prev_capital, current_capital)
            await message.answer(text)

        except Exception:
            logging.exception("ERROR in grow_asset")
            await message.answer(f"❌ Ошибка при расчёте роста капитала")


@asset_router.message(F.text == "/snapshot_asset")
async def create_snapshot(message: Message):
    """Обработчик команды /snapshot_asset: создаёт снэпшот текущего капитала."""
    
    user_id = message.from_user.id
    async with await get_session() as session:
        service = AssetService(session)
        
        try:
            success = await service.create_monthly_snapshot(user_id)

            if not success:
                await message.answer("📸 Снэпшот уже существует для этой даты.")
                return

            capital = await service.get_current_capital(user_id, ["RUB", "USD"])
            text = report_asset_snapshot_created(capital)
            await message.answer(text)

        except Exception:
            logging.exception("ERROR in create_snapshot")
            await message.answer(f"❌ Ошибка при создании снэпшота")


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

            # Определяем нераспознанные валюты: пробуем сконвертировать 1 ед. в USD
            unknown_currencies: set[str] = set()
            converter = AssetService(session).converter
            await converter.update_fiat_rates()
            await converter.update_crypto_rates()
            for cur in assets_by_currency.keys():
                try:
                    _ = await converter.convert(1.0, cur, "USD")
                except Exception:
                    unknown_currencies.add(cur)

            total_usd, total_rub, updated_at = await compute_totals_usd_rub(assets_by_currency)
            text = report_assets_detailed_list(assets_by_currency, total_usd, total_rub, updated_at, unknown_currencies)
            await message.answer(text, parse_mode="HTML")
            
        except Exception:
            logging.exception("ERROR in list_assets")
            await message.answer(f"❌ Ошибка при получении списка активов")
