from typing import Tuple, Optional, List, Dict
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entry, Currency
from app.utils.rates import CurrencyConverter


class EntryFetcher:
    """
    Класс для гибкой выгрузки и обработки данных о расходах и доходах из базы.
    """

    def __init__(self, session: AsyncSession, user_id: int):
        """
        :param session: Асинхронная сессия SQLAlchemy.
        :param user_id: ID пользователя (Telegram user_id).
        """
        self.session = session
        self.user_id = user_id
        self.converter = CurrencyConverter()  # можно внедрять извне для тестов

    async def fetch_entries(
        self,
        date_range: Tuple[datetime, datetime],
        mode: str,
        with_currency: bool = True
    ) -> Tuple[List[Entry], Dict[int, str]]:
        """
        Загружает записи пользователя за указанный период.

        :param date_range: Кортеж (start, end) с диапазоном дат.
        :param mode: Тип операции ("expense" или "income").
        :param with_currency: Нужно ли возвращать карту валют (id → код).
        :return: Список записей и карта валют (если запрошено).
        """
        start, end = date_range

        result = await self.session.execute(
            select(Entry)
            .where(Entry.user_id == self.user_id)
            .where(Entry.mode == mode)
            .where(Entry.created_at.between(start, end))
        )
        entries = result.scalars().all()

        if not entries:
            return [], {}

        if not with_currency:
            return entries, {}

        currency_ids = list(set(e.currency_id for e in entries if e.currency_id))
        currency_map = {}
        if currency_ids:
            currencies_result = await self.session.execute(
                select(Currency).where(Currency.id.in_(currency_ids))
            )
            currency_map = {c.id: c.code for c in currencies_result.scalars().all()}

        return entries, currency_map

    async def fetch_totals(
        self,
        date_range: Tuple[datetime, datetime],
        mode: str = "expense",
        group_by_currency: bool = False
    ) -> Dict[str, float]:
        """
        Считает суммы за период без конвертации.

        :param date_range: Кортеж (start, end).
        :param mode: Тип операции ("expense" или "income").
        :param group_by_currency: Если True, возвращает суммы по каждой валюте отдельно.
        :return: Словарь: { "RUB": сумма, "USD": сумма } или {"total": сумма}.
        """
        entries, currency_map = await self.fetch_entries(date_range, mode, with_currency=True)

        if not entries:
            return {}

        totals = {}
        for entry in entries:
            currency = currency_map.get(entry.currency_id, "USD")
            if group_by_currency:
                totals[currency] = totals.get(currency, 0) + float(entry.amount)
            else:
                totals["total"] = totals.get("total", 0) + float(entry.amount)

        return totals

    async def calculate_converted_totals(
        self,
        entries: List[Entry],
        currency_map: Dict[int, str],
        targets: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Конвертирует суммы в указанные валюты и возвращает агрегированные итоги.

        :param entries: Список записей Entry.
        :param currency_map: Словарь {id валюты: код валюты}.
        :param targets: Список валют для конвертации (по умолчанию ["RUB", "USD", "VND"]).
        :return: Словарь с итогами по валютам.
        """
        if not entries:
            return {}

        if targets is None:
            targets = ["RUB", "USD", "VND"]

        await self.converter.update_fiat_rates()
        await self.converter.update_crypto_rates()

        totals = {t: 0 for t in targets}
        for entry in entries:
            currency = currency_map.get(entry.currency_id, "USD")
            for target in targets:
                try:
                    converted = await self.converter.convert(float(entry.amount), currency, target)
                    totals[target] += converted
                except Exception as e:
                    print(f"[ERROR] Failed to convert {entry.amount} {currency} to {target}: {e}")
                    continue
        return totals
