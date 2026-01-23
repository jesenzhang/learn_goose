import logging
from typing import Any, List, Optional, Dict, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text, event
from sqlalchemy.engine import Engine

from .base import SQLDriver

logger = logging.getLogger("goose.persistence.drivers")

class SQLAlchemyDriver(SQLDriver):
    """
    通用 SQL 后端。
    同时支持 SQLite (本地) 和 PostgreSQL/MySQL (远程)。
    """
    def __init__(self, db_url: str, **engine_kwargs):
        if db_url.startswith("sqlite://") and "aiosqlite" not in db_url:
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

        self.db_url = db_url
        
        self.engine = create_async_engine(
            db_url,
            future=True,
            echo=False,
            **engine_kwargs
        )

        if "sqlite" in db_url:
            self._setup_sqlite_hooks()

    def _setup_sqlite_hooks(self):
        sync_engine = self.engine.sync_engine

        @event.listens_for(sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    async def connect(self):
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info(f"Connected to DB: {self.db_url}")

    async def close(self):
        await self.engine.dispose()

    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        async with self.engine.begin() as conn:
            result = await conn.execute(text(query), params or {})
            return result

    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        async with self.engine.connect() as conn:
            result = await conn.execute(text(query), params or {})
            return [dict(zip(result.keys(), row)) for row in result.fetchall()]

    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        async with self.engine.connect() as conn:
            result = await conn.execute(text(query), params or {})
            row = result.fetchone()
            return dict(zip(result.keys(), row)) if row else None

    async def execute_script(self, script: str) -> None:
        async with self.engine.begin() as conn:
            if "sqlite" in self.db_url:
                await conn.run_sync(lambda sync_conn: sync_conn.connection.executescript(script))
            else:
                for statement in script.split(';'):
                    if statement.strip():
                        await conn.execute(text(statement))

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        async with self.engine.begin():
            yield
