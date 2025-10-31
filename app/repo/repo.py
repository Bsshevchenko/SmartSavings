from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Currency, Category, Entry
from app.services.asset_service import AssetService

# users
async def ensure_user(session: AsyncSession, user_id: int, username: Optional[str]) -> None:
    u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        session.add(User(id=user_id, username=username))
    else:
        u.username = username or u.username
    await session.commit()

# currencies
async def add_custom_currency(session: AsyncSession, user_id: int, code: str) -> None:
    code = (code or "").strip()
    if not code:
        return
    exists = (await session.execute(
        select(Currency.id).where(Currency.user_id == user_id, Currency.code.ilike(code))
    )).scalar_one_or_none()
    if exists is None:
        session.add(Currency(user_id=user_id, code=code))
        await session.commit()

async def list_user_currencies(session: AsyncSession, user_id: int) -> List[str]:
    # Сортируем по last_used_at DESC (последние использованные сначала), затем по id DESC
    rows = (await session.execute(
        select(Currency.code)
        .where(Currency.user_id == user_id)
        .order_by(
            Currency.last_used_at.desc().nulls_last(),
            Currency.id.desc()
        )
    )).scalars().all()
    return rows

async def update_currency_last_used(session: AsyncSession, user_id: int, code: str) -> None:
    """Обновляет время последнего использования валюты."""
    cur = (await session.execute(
        select(Currency).where(Currency.user_id == user_id, Currency.code.ilike(code))
    )).scalar_one_or_none()
    if cur:
        cur.last_used_at = datetime.now(timezone.utc)
        await session.flush()

# categories
async def add_custom_category(session: AsyncSession, user_id: int, mode: str, name: str) -> None:
    name = (name or "").strip()
    if not name:
        return
    exists = (await session.execute(
        select(Category.id).where(Category.user_id == user_id, Category.mode == mode, Category.name.ilike(name))
    )).scalar_one_or_none()
    if exists is None:
        session.add(Category(user_id=user_id, mode=mode, name=name))
        await session.commit()

async def list_user_categories(session: AsyncSession, user_id: int, mode: str) -> List[str]:
    # Сортируем по last_used_at DESC (последние использованные сначала), затем по id DESC
    rows = (await session.execute(
        select(Category.name)
        .where(Category.user_id == user_id, Category.mode == mode)
        .order_by(
            Category.last_used_at.desc().nulls_last(),
            Category.id.desc()
        )
    )).scalars().all()
    return rows

async def update_category_last_used(session: AsyncSession, user_id: int, mode: str, name: str) -> None:
    """Обновляет время последнего использования категории."""
    cat = (await session.execute(
        select(Category).where(Category.user_id == user_id, Category.mode == mode, Category.name.ilike(name))
    )).scalar_one_or_none()
    if cat:
        cat.last_used_at = datetime.now(timezone.utc)
        await session.flush()

# entries
async def add_entry(
    session: AsyncSession,
    user_id: int,
    mode: str,
    amount: Decimal,
    currency_code: str,
    category_name: str | None,
    note: str | None = None,
) -> int:
    # ensure currency
    cur = (await session.execute(
        select(Currency).where(Currency.user_id == user_id, Currency.code.ilike(currency_code))
    )).scalar_one_or_none()
    if cur is None:
        cur = Currency(user_id=user_id, code=currency_code)
        session.add(cur)
        await session.flush()

    cat_id = None
    if category_name:
        cat = (await session.execute(
            select(Category).where(Category.user_id == user_id, Category.mode == mode, Category.name.ilike(category_name))
        )).scalar_one_or_none()
        if cat is None:
            cat = Category(user_id=user_id, mode=mode, name=category_name)
            session.add(cat)
            await session.flush()
        cat_id = cat.id

    entry = Entry(user_id=user_id, mode=mode, amount=amount, currency_id=cur.id, category_id=cat_id, note=note)
    session.add(entry)
    await session.flush()  # Используем flush для получения ID
    
    # Обновляем last_used_at для валюты и категории при сохранении записи
    cur.last_used_at = datetime.now(timezone.utc)
    if cat:
        cat.last_used_at = datetime.now(timezone.utc)
    
    # Если это актив, обновляем последние значения и сохраняем курсы
    if mode == "asset":
        analytics_service = AssetService(session)
        await analytics_service.update_latest_asset_value(user_id, currency_code, category_name, amount, entry.id)
        await analytics_service.save_current_rates(currency_code)
    
    await session.commit()
    return entry.id

# snapshot для прогрева in-memory клавиатур
async def get_user_prefs_snapshot(session: AsyncSession, user_id: int) -> dict:
    return {
        "currencies": await list_user_currencies(session, user_id),
        "categories": {
            "income": await list_user_categories(session, user_id, "income"),
            "expense": await list_user_categories(session, user_id, "expense"),
            "asset":  await list_user_categories(session, user_id, "asset"),
        }
    }
