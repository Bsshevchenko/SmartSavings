from __future__ import annotations
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Column, Integer, String, Numeric, DateTime, Date,
    ForeignKey, UniqueConstraint, Index, CheckConstraint, event
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ModeEnum(str, enum.Enum):
    income = "income"
    expense = "expense"
    asset = "asset"

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)  # telegram user_id
    username = Column(String(64), nullable=True)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    currencies = relationship("Currency", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    entries    = relationship("Entry", back_populates="user", cascade="all, delete-orphan")

class Currency(Base):
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), nullable=False)  # напр. USD, USDT, тенге, USDC, ...
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)  # время последнего использования

    user = relationship("User", back_populates="currencies")

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_currency_user_code"),
        Index("ix_currency_user_code", "user_id", "code"),
        Index("ix_currency_user_last_used", "user_id", "last_used_at"),
    )

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    mode = Column(String(16), nullable=False)  # 'income' | 'expense' | 'asset'
    name = Column(String(64), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)  # время последнего использования

    user = relationship("User", back_populates="categories")

    __table_args__ = (
        CheckConstraint("mode in ('income','expense','asset')", name="ck_category_mode"),
        UniqueConstraint("user_id", "mode", "name", name="uq_category_user_mode_name"),
        Index("ix_category_user_mode_name", "user_id", "mode", "name"),
        Index("ix_category_user_mode_last_used", "user_id", "mode", "last_used_at"),
    )

class Entry(Base):
    __tablename__ = "entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode = Column(String(16), nullable=False)  # income/expense/asset
    amount = Column(Numeric(28, 10), nullable=False)  # Decimal
    currency_id = Column(Integer, ForeignKey("currencies.id", ondelete="SET NULL"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    note = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="entries")
    currency = relationship("Currency")
    category = relationship("Category")

    __table_args__ = (
        CheckConstraint("mode in ('income','expense','asset')", name="ck_entry_mode"),
        Index("ix_entry_user_created_at", "user_id", "created_at"),
    )

class CapitalSnapshot(Base):
    """Снэпшоты капитала на определённые даты для корректного анализа динамики."""
    __tablename__ = "capital_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    total_usd = Column(Numeric(28, 10), nullable=False)
    total_rub = Column(Numeric(28, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User")
    
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_capital_snapshot_user_date"),
        Index("ix_capital_snapshot_user_date", "user_id", "snapshot_date"),
    )

class CurrencyRate(Base):
    """Исторические курсы валют для корректных расчётов динамики капитала."""
    __tablename__ = "currency_rates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    currency_code = Column(String(10), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate_to_usd = Column(Numeric(20, 10), nullable=False)
    source = Column(String(50), nullable=False, default="api")  # 'api', 'manual'
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        UniqueConstraint("currency_code", "rate_date", name="uq_currency_rate_code_date"),
        Index("ix_currency_rate_code_date", "currency_code", "rate_date"),
    )

class AssetLatestValues(Base):
    """Последние значения активов пользователя для быстрого расчёта текущего капитала."""
    __tablename__ = "asset_latest_values"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    currency_code = Column(String(10), nullable=False)
    category_name = Column(String(64), nullable=True)  # Добавляем категорию
    amount = Column(Numeric(28, 10), nullable=False)
    last_updated = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    entry_id = Column(Integer, ForeignKey("entries.id", ondelete="SET NULL"), nullable=True)
    
    user = relationship("User")
    entry = relationship("Entry")
    
    __table_args__ = (
        UniqueConstraint("user_id", "currency_code", "category_name", name="uq_asset_latest_user_currency_category"),
        Index("ix_asset_latest_user_currency_category", "user_id", "currency_code", "category_name"),
    )
