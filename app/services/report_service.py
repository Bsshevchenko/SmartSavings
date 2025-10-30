"""
Сервис для формирования отчетов по расходам и доходам.
"""
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entry, Currency
from app.services.rates import CurrencyConverter

logger = logging.getLogger(__name__)


class ReportService:
    """Сервис для формирования отчетов по расходам и доходам."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.converter = CurrencyConverter()
    
    async def get_entries_for_period(
        self,
        user_id: int,
        date_range: Tuple[datetime, datetime],
        mode: str
    ) -> Tuple[List[Entry], Dict[int, str]]:
        """
        Загружает записи пользователя за указанный период.
        
        Args:
            user_id: ID пользователя
            date_range: Кортеж (start, end) с диапазоном дат
            mode: Тип операции ("expense", "income", "asset")
            
        Returns:
            Список записей и карта валют (id → код)
        """
        start, end = date_range

        result = await self.session.execute(
            select(Entry)
            .where(Entry.user_id == user_id)
            .where(Entry.mode == mode)
            .where(Entry.created_at.between(start, end))
        )
        entries = result.scalars().all()

        if not entries:
            return [], {}

        # Получаем карту валют
        currency_ids = list(set(e.currency_id for e in entries if e.currency_id))
        currency_map = {}
        if currency_ids:
            currencies_result = await self.session.execute(
                select(Currency).where(Currency.id.in_(currency_ids))
            )
            currency_map = {c.id: c.code for c in currencies_result.scalars().all()}

        return entries, currency_map
    
    async def calculate_converted_totals(
        self,
        entries: List[Entry],
        currency_map: Dict[int, str],
        target_currencies: List[str] = None
    ) -> Dict[str, float]:
        """
        Конвертирует суммы в указанные валюты и возвращает агрегированные итоги.
        
        Args:
            entries: Список записей Entry
            currency_map: Словарь {id валюты: код валюты}
            target_currencies: Список валют для конвертации (по умолчанию ["RUB", "USD", "VND"])
            
        Returns:
            Словарь с итогами по валютам
        """
        if not entries:
            return {}

        if target_currencies is None:
            target_currencies = ["RUB", "USD", "VND"]

        await self.converter.update_fiat_rates()
        await self.converter.update_crypto_rates()

        totals = {currency: 0.0 for currency in target_currencies}
        for entry in entries:
            currency = currency_map.get(entry.currency_id, "USD")
            for target in target_currencies:
                try:
                    converted = await self.converter.convert(float(entry.amount), currency, target)
                    totals[target] += converted
                except Exception as e:
                    logger.error(f"Failed to convert {entry.amount} {currency} to {target}: {e}")
                    continue
        return totals
    
    async def get_period_totals(
        self,
        user_id: int,
        date_range: Tuple[datetime, datetime],
        mode: str,
        target_currencies: List[str] = None
    ) -> Dict[str, float]:
        """
        Получает итоги за период с конвертацией валют.
        
        Args:
            user_id: ID пользователя
            date_range: Кортеж (start, end) с диапазоном дат
            mode: Тип операции ("expense", "income", "asset")
            target_currencies: Список валют для конвертации
            
        Returns:
            Словарь с итогами по валютам
        """
        entries, currency_map = await self.get_entries_for_period(user_id, date_range, mode)
        return await self.calculate_converted_totals(entries, currency_map, target_currencies)
