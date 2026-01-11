import aiosqlite
import logging
import os
from typing import List, Any, Dict, Optional
from .base import SQLDriver
logger = logging.getLogger("goose.persistence.sqlite")

class SQLiteDriver(SQLDriver):
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self._conn:
            return

        logger.info(f"🔌 Connecting to SQLite: {self.db_path}")
        self._conn = await aiosqlite.connect(self.db_path)
        
        # [关键优化] 设置 Row Factory，使查询结果可以像字典一样访问
        self._conn.row_factory = aiosqlite.Row

        # [关键优化] 开启 WAL 模式以支持高并发 (一写多读)
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        
        # [关键优化] 开启外键约束
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("🔌 Disconnected from SQLite")

    async def execute(self, query: str, params: tuple = ()) -> None:
        if not self._conn: await self.connect()
        async with self._conn.cursor() as cursor:
            await cursor.execute(query, params)
            await self._conn.commit()

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        if not self._conn: await self.connect()
        async with self._conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        if not self._conn: await self.connect()
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
            
    async def execute_script(self, script: str) -> None:
        if not self._conn: await self.connect()
        await self._conn.executescript(script)
        await self._conn.commit()