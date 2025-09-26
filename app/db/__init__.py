from __future__ import annotations

import os
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base
from app.config import settings


DB_URL = settings.DB_URL

engine = create_async_engine(
    url=settings.DB_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite+") else {},
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, autoflush=False, expire_on_commit=False
)

# SQLite тюнинг: WAL + foreign_keys
@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, connection_record):
    if DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

async def init_db():
    # создать папку, если надо
    if DB_URL.startswith("sqlite+"):
        path = DB_URL.split("///", 1)[-1]
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    return SessionLocal()
