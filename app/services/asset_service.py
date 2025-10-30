"""
Единый сервис для работы с активами и капиталом.
Объединяет функциональность CapitalAnalyticsService и EntryFetcher.
"""
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Entry, Currency, Category, CapitalSnapshot, CurrencyRate, AssetLatestValues, User
)
from app.services.rates import CurrencyConverter

logger = logging.getLogger(__name__)


class AssetService:
    """Единый сервис для работы с активами и капиталом."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.converter = CurrencyConverter()
    
    async def get_current_capital(self, user_id: int, target_currencies: List[str] = None) -> Dict[str, float]:
        """
        Получает актуальный капитал по последним значениям каждого актива.
        
        Args:
            user_id: ID пользователя
            target_currencies: Список валют для конвертации (по умолчанию ["RUB", "USD"])
            
        Returns:
            Словарь с капиталом по валютам: {"RUB": 1000.0, "USD": 50.0}
        """
        if target_currencies is None:
            target_currencies = ["RUB", "USD"]
        
        # Получаем последние значения по каждому активу
        latest_assets = await self.session.execute(
            select(AssetLatestValues)
            .where(AssetLatestValues.user_id == user_id)
        )
        
        assets = latest_assets.scalars().all()
        if not assets:
            return {currency: 0.0 for currency in target_currencies}
        
        # Получаем текущие курсы
        await self.converter.update_fiat_rates()
        await self.converter.update_crypto_rates()
        
        # Инициализируем итоги
        totals = {currency: 0.0 for currency in target_currencies}
        
        # Конвертируем каждый актив в целевые валюты
        for asset in assets:
            for target_currency in target_currencies:
                try:
                    converted = await self.converter.convert(
                        float(asset.amount), 
                        asset.currency_code, 
                        target_currency
                    )
                    totals[target_currency] += converted
                except Exception as e:
                    logger.error(f"Failed to convert {asset.amount} {asset.currency_code} to {target_currency}: {e}")
                    
        return totals
    
    async def get_capital_for_date(self, user_id: int, target_date: date, target_currencies: List[str] = None) -> Dict[str, float]:
        """
        Получает капитал на определённую дату.
        Использует снэпшоты или пересчитывает по историческим курсам.
        """
        if target_currencies is None:
            target_currencies = ["RUB", "USD"]
        
        # Сначала ищем готовый снэпшот
        snapshot = await self.session.execute(
            select(CapitalSnapshot)
            .where(CapitalSnapshot.user_id == user_id)
            .where(CapitalSnapshot.snapshot_date == target_date)
        )
        
        snapshot_result = snapshot.scalar_one_or_none()
        if snapshot_result:
            result = {}
            for currency in target_currencies:
                if currency == "USD":
                    result[currency] = float(snapshot_result.total_usd)
                elif currency == "RUB":
                    result[currency] = float(snapshot_result.total_rub)
                else:
                    # Конвертируем из USD в нужную валюту
                    await self.converter.update_fiat_rates()
                    result[currency] = await self.converter.convert(
                        float(snapshot_result.total_usd), "USD", currency
                    )
            return result
        
        # Если снэпшота нет, пересчитываем по историческим данным
        return await self._recalculate_capital_for_date(user_id, target_date, target_currencies)
    
    async def _recalculate_capital_for_date(self, user_id: int, target_date: date, target_currencies: List[str]) -> Dict[str, float]:
        """
        Пересчитывает капитал на определённую дату по историческим данным.
        """
        # Получаем все активы пользователя на указанную дату
        assets_query = await self.session.execute(
            select(Entry.currency_id, Entry.category_id, Entry.amount, Entry.created_at)
            .where(Entry.user_id == user_id)
            .where(Entry.mode == "asset")
            .where(Entry.created_at <= datetime.combine(target_date, datetime.max.time(), timezone.utc))
            .order_by(Entry.currency_id, Entry.category_id, Entry.created_at.desc())
        )
        
        entries = assets_query.all()
        if not entries:
            return {currency: 0.0 for currency in target_currencies}
        
        # Группируем по валюте + категории и берём последние значения на указанную дату
        asset_latest = {}
        for currency_id, category_id, amount, created_at in entries:
            key = (currency_id, category_id)
            if key not in asset_latest:
                asset_latest[key] = (amount, created_at)
        
        # Получаем коды валют и категорий
        currency_ids = list(set(key[0] for key in asset_latest.keys() if key[0] is not None))
        category_ids = list(set(key[1] for key in asset_latest.keys() if key[1] is not None))
        
        currencies = {}
        if currency_ids:
            currency_result = await self.session.execute(
                select(Currency).where(Currency.id.in_(currency_ids))
            )
            currencies = {c.id: c.code for c in currency_result.scalars().all()}
        
        categories = {}
        if category_ids:
            category_result = await self.session.execute(
                select(Category).where(Category.id.in_(category_ids))
            )
            categories = {c.id: c.name for c in category_result.scalars().all()}
        
        # Конвертируем по историческим курсам
        totals = {currency: 0.0 for currency in target_currencies}
        for (currency_id, category_id), (amount, created_at) in asset_latest.items():
            currency_code = currencies.get(currency_id, "USD")
            try:
                # Используем исторический курс
                rate = await self.get_historical_rate(currency_code, target_date)
                amount_in_usd = float(amount) * rate
                
                for target_currency in target_currencies:
                    if target_currency == "USD":
                        totals[target_currency] += amount_in_usd
                    else:
                        # Конвертируем из USD в целевую валюту
                        await self.converter.update_fiat_rates()
                        converted = await self.converter.convert(amount_in_usd, "USD", target_currency)
                        totals[target_currency] += converted
                        
            except Exception as e:
                logger.error(f"Failed to convert {amount} {currency_code} for date {target_date}: {e}")
                
        return totals
    
    async def get_historical_rate(self, currency_code: str, target_date: date) -> float:
        """
        Получает исторический курс валюты на определённую дату.
        """
        # Ищем точный курс на дату
        rate_query = await self.session.execute(
            select(CurrencyRate.rate_to_usd)
            .where(CurrencyRate.currency_code == currency_code)
            .where(CurrencyRate.rate_date == target_date)
        )
        
        rate = rate_query.scalar_one_or_none()
        if rate:
            return float(rate)
        
        # Если нет точного курса, берём ближайший предыдущий
        nearest_query = await self.session.execute(
            select(CurrencyRate.rate_to_usd)
            .where(CurrencyRate.currency_code == currency_code)
            .where(CurrencyRate.rate_date <= target_date)
            .order_by(CurrencyRate.rate_date.desc())
            .limit(1)
        )
        
        rate = nearest_query.scalar_one_or_none()
        if rate:
            return float(rate)
        
        # Если исторических данных нет, используем текущий курс
        logger.warning(f"No historical rate found for {currency_code} on {target_date}, using current rate")
        await self.converter.update_fiat_rates()
        await self.converter.update_crypto_rates()
        return await self.converter.convert(1.0, currency_code, "USD")
    
    async def create_monthly_snapshot(self, user_id: int, target_date: Optional[date] = None) -> bool:
        """
        Создаёт снэпшот капитала на определённую дату.
        """
        if target_date is None:
            target_date = date.today()
        
        # Проверяем, нет ли уже снэпшота
        existing = await self.session.execute(
            select(CapitalSnapshot.id)
            .where(CapitalSnapshot.user_id == user_id)
            .where(CapitalSnapshot.snapshot_date == target_date)
        )
        
        if existing.scalar_one_or_none():
            return False  # Снэпшот уже существует
        
        try:
            # Получаем капитал на указанную дату
            capital = await self.get_capital_for_date(user_id, target_date, ["USD", "RUB"])
            
            # Сохраняем снэпшот
            snapshot = CapitalSnapshot(
                user_id=user_id,
                snapshot_date=target_date,
                total_usd=capital["USD"],
                total_rub=capital["RUB"]
            )
            self.session.add(snapshot)
            await self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            await self.session.rollback()
            return False
    
    async def update_latest_asset_value(self, user_id: int, currency_code: str, category_name: str, amount: Decimal, entry_id: int) -> None:
        """
        Обновляет последнее значение актива пользователя.
        """
        # Используем upsert для обновления или создания записи
        existing = await self.session.execute(
            select(AssetLatestValues)
            .where(AssetLatestValues.user_id == user_id)
            .where(AssetLatestValues.currency_code == currency_code)
            .where(AssetLatestValues.category_name == category_name)
        )
        
        asset_value = existing.scalar_one_or_none()
        if asset_value:
            # Обновляем существующую запись
            asset_value.amount = amount
            asset_value.last_updated = datetime.now(timezone.utc)
            asset_value.entry_id = entry_id
        else:
            # Создаём новую запись
            asset_value = AssetLatestValues(
                user_id=user_id,
                currency_code=currency_code,
                category_name=category_name,
                amount=amount,
                entry_id=entry_id
            )
            self.session.add(asset_value)
        
        await self.session.commit()
    
    async def get_detailed_assets_list(self, user_id: int) -> List[Dict]:
        """
        Получает детальный список всех активов пользователя.
        """
        result = await self.session.execute(
            select(AssetLatestValues)
            .where(AssetLatestValues.user_id == user_id)
            .order_by(AssetLatestValues.currency_code, AssetLatestValues.category_name)
        )
        assets = result.scalars().all()
        
        if not assets:
            return []
        
        # Группируем активы по валютам
        assets_by_currency = {}
        for asset in assets:
            currency = asset.currency_code
            if currency not in assets_by_currency:
                assets_by_currency[currency] = []
            assets_by_currency[currency].append(asset)
        
        return assets_by_currency
    
    async def save_current_rates(self, currency_code: str) -> None:
        """
        Сохраняет текущие курсы валют для исторических расчётов.
        """
        today = date.today()
        
        # Проверяем, есть ли уже курс на сегодня
        existing = await self.session.execute(
            select(CurrencyRate.id)
            .where(CurrencyRate.currency_code == currency_code)
            .where(CurrencyRate.rate_date == today)
        )
        
        if existing.scalar_one_or_none():
            return  # Курс уже сохранён
        
        # Получаем текущий курс
        await self.converter.update_fiat_rates()
        await self.converter.update_crypto_rates()
        
        try:
            rate_to_usd = await self.converter.convert(1.0, currency_code, "USD")
            
            rate = CurrencyRate(
                currency_code=currency_code,
                rate_date=today,
                rate_to_usd=rate_to_usd,
                source="api"
            )
            self.session.add(rate)
            await self.session.commit()
        except Exception as e:
            logger.error(f"Failed to save rate for {currency_code}: {e}")
