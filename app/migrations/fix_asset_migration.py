#!/usr/bin/env python3
"""
Исправленная миграция активов с учётом категорий
"""
import asyncio
import logging
import sys
import os
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select

# Добавляем путь к приложению
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Base, Entry, Currency, Category

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_migration_session():
    """Получает сессию для миграции."""
    import os
    
    # Используем путь к базе данных напрямую
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "app.db")
    db_url = f"sqlite+aiosqlite:///{db_path}"
    
    engine = create_async_engine(db_url)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SessionLocal()

async def recreate_asset_latest_values_table():
    """Пересоздаёт таблицу asset_latest_values с учётом категорий."""
    import os
    
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "app.db")
    db_url = f"sqlite+aiosqlite:///{db_path}"
    
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # Удаляем старую таблицу
        await conn.execute(text("DROP TABLE IF EXISTS asset_latest_values"))
        
        # Создаём новую таблицу
        await conn.execute(text("""
            CREATE TABLE asset_latest_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT NOT NULL,
                currency_code VARCHAR(10) NOT NULL,
                category_name VARCHAR(64),
                amount NUMERIC(28, 10) NOT NULL,
                last_updated DATETIME NOT NULL,
                entry_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE SET NULL
            )
        """))
        
        # Создаём индексы и ограничения
        await conn.execute(text("""
            CREATE UNIQUE INDEX uq_asset_latest_user_currency_category 
            ON asset_latest_values (user_id, currency_code, category_name)
        """))
        
        await conn.execute(text("""
            CREATE INDEX ix_asset_latest_user_currency_category 
            ON asset_latest_values (user_id, currency_code, category_name)
        """))
    
    await engine.dispose()
    logger.info("✅ Таблица asset_latest_values пересоздана с учётом категорий")

async def migrate_assets_with_categories():
    """
    Мигрирует активы с учётом категорий.
    """
    async with await get_migration_session() as session:
        # Получаем всех пользователей с активами
        users_result = await session.execute(
            text("SELECT DISTINCT user_id FROM entries WHERE mode = 'asset'")
        )
        user_ids = [row[0] for row in users_result.fetchall()]
        
        logger.info(f"📊 Найдено {len(user_ids)} пользователей с активами")
        
        for user_id in user_ids:
            logger.info(f"🔄 Обрабатываем пользователя {user_id}")
            
            # Получаем последние записи по каждой комбинации валюта + категория
            latest_assets_result = await session.execute(
                text("""
                    SELECT 
                        c.code as currency_code,
                        cat.name as category_name,
                        e.amount,
                        e.created_at,
                        e.id as entry_id
                    FROM entries e
                    LEFT JOIN currencies c ON e.currency_id = c.id
                    LEFT JOIN categories cat ON e.category_id = cat.id
                    WHERE e.user_id = :user_id AND e.mode = 'asset'
                    AND (e.currency_id, e.category_id, e.created_at) IN (
                        SELECT currency_id, category_id, MAX(created_at)
                        FROM entries e2
                        WHERE e2.user_id = e.user_id 
                        AND e2.mode = 'asset'
                        GROUP BY currency_id, category_id
                    )
                """),
                {"user_id": user_id}
            )
            
            latest_assets = latest_assets_result.fetchall()
            logger.info(f"  Найдено {len(latest_assets)} уникальных активов")
            
            for currency_code, category_name, amount, created_at, entry_id in latest_assets:
                # Сохраняем в новую таблицу
                await session.execute(
                    text("""
                        INSERT INTO asset_latest_values 
                        (user_id, currency_code, category_name, amount, last_updated, entry_id)
                        VALUES (:user_id, :currency_code, :category_name, :amount, :created_at, :entry_id)
                    """),
                    {
                        "user_id": user_id,
                        "currency_code": currency_code,
                        "category_name": category_name,
                        "amount": amount,
                        "created_at": created_at,
                        "entry_id": entry_id
                    }
                )
                logger.info(f"    Сохранён актив: {currency_code} {category_name} = {amount}")
            
            await session.commit()
        
        logger.info("✅ Миграция активов с категориями завершена")

async def verify_migration():
    """Проверяет результаты миграции."""
    async with await get_migration_session() as session:
        # Проверяем количество активов
        result = await session.execute(
            text("SELECT COUNT(*) FROM asset_latest_values")
        )
        total_assets = result.scalar()
        
        # Проверяем активы пользователя 614688432
        result = await session.execute(
            text("""
                SELECT currency_code, category_name, amount 
                FROM asset_latest_values 
                WHERE user_id = 614688432
                ORDER BY currency_code, category_name
            """)
        )
        user_assets = result.fetchall()
        
        logger.info(f"📊 Всего активов в новой таблице: {total_assets}")
        logger.info(f"📊 Активы пользователя 614688432:")
        
        total_rub = 0
        for currency_code, category_name, amount in user_assets:
            logger.info(f"  • {currency_code} {category_name}: {amount}")
            if currency_code == "RUB":
                total_rub += float(amount)
        
        logger.info(f"💰 Общая сумма в RUB: {total_rub:,.2f}")

async def main():
    logger.info("🚀 Начинаем исправленную миграцию активов с учётом категорий")
    await recreate_asset_latest_values_table()
    await migrate_assets_with_categories()
    await verify_migration()
    logger.info("🎉 Исправленная миграция завершена!")

if __name__ == "__main__":
    asyncio.run(main())
