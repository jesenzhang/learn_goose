import logging
from typing import Any, List, Optional, Dict, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text, event
from sqlalchemy.engine import Engine

from goose.persistence.backend import StorageBackend

logger = logging.getLogger("goose.persistence.drivers")

class SQLAlchemyBackend(StorageBackend):
    """
    通用 SQL 后端。
    同时支持 SQLite (本地) 和 PostgreSQL/MySQL (远程)。
    """
    def __init__(self, db_url: str, **engine_kwargs):
        # 1. 针对 SQLite 的特殊 URL 处理
        # 如果用户只传了 "sqlite:///test.db"，自动补全异步驱动名
        if db_url.startswith("sqlite://") and "aiosqlite" not in db_url:
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

        self.db_url = db_url
        
        # 2. 创建引擎
        self.engine = create_async_engine(
            db_url,
            future=True,
            echo=False,
            **engine_kwargs
        )

        # 3. [关键] 针对 SQLite 的特殊配置 (Hook)
        if "sqlite" in db_url:
            self._setup_sqlite_hooks()

    def _setup_sqlite_hooks(self):
        """
        为 SQLite 配置特殊指令：
        1. 开启外键约束 (PRAGMA foreign_keys=ON)
        2. 开启 WAL 模式 (性能优化)
        """
        # 获取底层的同步引擎类 (SQLAlchemy Core)
        sync_engine = self.engine.sync_engine

        @event.listens_for(sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            # 这里的 dbapi_connection 就是底层的 sqlite3 连接对象
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    async def connect(self):
        # SQLAlchemy 是懒加载的，执行一个简单查询来触发连接
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info(f"🔌 Connected to DB: {self.db_url}")

    async def close(self):
        await self.engine.dispose()

    # ==========================================
    # 数据操作
    # ==========================================

    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        async with self.engine.begin() as conn:
            # 自动处理 :key 参数
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

    # ==========================================
    # 特殊功能
    # ==========================================

    async def execute_script(self, script: str) -> None:
        """
        执行多条 SQL 语句的脚本。
        SQLAlchemy 的 execute 默认不支持多语句。
        我们需要下沉到底层驱动来执行。
        """
        async with self.engine.begin() as conn:
            if "sqlite" in self.db_url:
                # [关键] 针对 SQLite，调用 run_sync 使用原生 executescript
                await conn.run_sync(lambda sync_conn: sync_conn.connection.executescript(script))
            else:
                # 针对 Postgres/MySQL，通常按分号分割执行即可，或者直接透传
                # 这里简单实现为按分号分割
                for statement in script.split(';'):
                    if statement.strip():
                        await conn.execute(text(statement))

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """事务上下文"""
        # SQLAlchemy 的 begin() 块本身就是事务
        async with self.engine.begin():
            yield