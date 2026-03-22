"""
ingestion/database.py  —  Database Engine & Session Management
══════════════════════════════════════════════════════════════
Поддерживает:
  · SQLite  (разработка / демо, по умолчанию)
  · PostgreSQL  (продакшн, переключается через DATABASE_URL)

▶ НАСТРОЙТЕ в .env:
    DATABASE_URL=sqlite:///./data/bilb.db
    # или
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/bilb
"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("bilb.db")

# ── URL ───────────────────────────────────────────────────────
# SQLite → автоматически конвертируем sync URL в async
_RAW_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/bilb.db")

def _make_async_url(url: str) -> str:
    """sqlite:/// → sqlite+aiosqlite:///  |  postgresql → postgresql+asyncpg"""
    if url.startswith("sqlite") and "aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql") and "asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL: str = _make_async_url(_RAW_URL)

# ── Engine ────────────────────────────────────────────────────
_is_sqlite = DATABASE_URL.startswith("sqlite")

# NullPool for file-based SQLite: каждая сессия открывает свой fd к файлу,
# все пишут в один .db → таблицы видны всем. NullPool не кэширует соединения,
# что гарантирует актуальность схемы между create_tables() и session-запросами.
# StaticPool только для in-memory тестов. PostgreSQL — стандартный QueuePool.
from sqlalchemy.pool import NullPool as _NullPool, StaticPool as _StaticPool

if ":memory:" in DATABASE_URL:
    _pool_kw: dict = {
        "poolclass":    _StaticPool,
        "connect_args": {"check_same_thread": False},
    }
elif _is_sqlite:
    _pool_kw = {"poolclass": _NullPool}
else:
    _pool_kw = {
        "pool_size":    5,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    **_pool_kw,
)

# SQLite pragmas: применяем через event только для NullPool
# (WAL не нужен при NullPool — нет конкурентных читателей в пуле)
if _is_sqlite and ":memory:" not in DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# ── Session factory ───────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # объекты живут после commit()
    autoflush=False,
    autocommit=False,
)

# ── Base class для всех моделей ───────────────────────────────
class Base(DeclarativeBase):
    pass

# ── Зависимость FastAPI (Dependency Injection) ────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Использование в роутерах:
        async def endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# ── Context manager для bridge / скриптов (вне FastAPI) ───────
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Использование вне FastAPI:
        async with db_session() as session:
            session.add(obj)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# ── Создание всех таблиц ──────────────────────────────────────
async def create_tables() -> None:
    """Создаёт таблицы если не существуют. Вызвать при старте приложения."""
    import os
    os.makedirs("data", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Tables ready: %s", list(Base.metadata.tables.keys()))

# ── Health check ──────────────────────────────────────────────
async def ping_db() -> bool:
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.error("DB ping failed: %s", exc)
        return False
