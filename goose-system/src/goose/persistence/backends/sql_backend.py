"""
SQL Backend

SQL database backend implementation.
Reference: pho persistence SQL backend.
"""

import logging
from typing import Any, Dict, List, Tuple, Optional
from contextlib import asynccontextmanager
from abc import ABC, abstractmethod

from ..backend import PersistenceBackend

logger = logging.getLogger("goose.persistence.sql")


class SQLDriver:
    """Abstract SQL driver interface."""

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def execute(self, sql: str, params: Dict = None) -> Any:
        pass

    @abstractmethod
    async def fetch_one(self, sql: str, params: Dict = None) -> Optional[Dict]:
        pass

    @abstractmethod
    async def fetch_all(self, sql: str, params: Dict = None) -> List[Dict]:
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self):
        yield


class SQLiteDriver(SQLDriver):
    """SQLite driver using aiosqlite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None

    async def connect(self):
        try:
            import aiosqlite
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
        except ImportError:
            raise ImportError("aiosqlite required for SQLite. Install: pip install aiosqlite")

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: Dict = None):
        cursor = await self._conn.execute(sql, params or {})
        await self._conn.commit()
        return cursor

    async def fetch_one(self, sql: str, params: Dict = None):
        cursor = await self._conn.execute(sql, params or {})
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return dict(zip([c[0] for c in cursor.description], row))
        return None

    async def fetch_all(self, sql: str, params: Dict = None):
        cursor = await self._conn.execute(sql, params or {})
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(zip([c[0] for c in cursor.description], row)) for row in rows]

    @asynccontextmanager
    async def transaction(self):
        async with self._conn:
            yield


class SQLBackend(PersistenceBackend):
    """
    SQL backend adapter.

    Translates generic operations to SQL statements.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.driver: SQLDriver = self._create_driver()

    def _create_driver(self) -> SQLDriver:
        """Create appropriate SQL driver."""
        if self.db_url.startswith("sqlite"):
            path = self.db_url.replace("sqlite://", "").replace("sqlite:///", "")
            return SQLiteDriver(path)
        raise ValueError(f"Unsupported SQL dialect: {self.db_url}")

    async def boot(self, schemas: List[Dict]) -> None:
        await self.driver.connect()
        for item in schemas:
            if isinstance(item, str) and item.strip():
                try:
                    await self.driver.execute(item)
                except Exception as e:
                    logger.error(f"Failed to execute schema: {e}")
            elif isinstance(item, list):
                for sql in item:
                    if sql.strip():
                        try:
                            await self.driver.execute(sql)
                        except Exception as e:
                            logger.error(f"Failed to execute schema: {e}")

    async def close(self):
        await self.driver.close()

    def _build_where(self, filters: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Build WHERE clause from filters."""
        if not filters:
            return "1=1", {}

        clauses = []
        params = {}
        param_idx = 0

        for field, value in filters.items():
            if isinstance(value, dict):
                for op, op_val in value.items():
                    param_key = f"p_{param_idx}_{field}"
                    param_idx += 1

                    if op == "$eq":
                        clauses.append(f"{field} = :{param_key}")
                    elif op == "$ne":
                        clauses.append(f"{field} != :{param_key}")
                    elif op == "$gt":
                        clauses.append(f"{field} > :{param_key}")
                    elif op == "$gte":
                        clauses.append(f"{field} >= :{param_key}")
                    elif op == "$lt":
                        clauses.append(f"{field} < :{param_key}")
                    elif op == "$lte":
                        clauses.append(f"{field} <= :{param_key}")
                    elif op == "$like":
                        clauses.append(f"{field} LIKE :{param_key}")
                    elif op == "$in":
                        clauses.append(f"{field} IN :{param_key}")
                    else:
                        raise ValueError(f"Unknown operator: {op}")

                    params[param_key] = op_val
            else:
                param_key = f"p_{param_idx}_{field}"
                param_idx += 1
                clauses.append(f"{field} = :{param_key}")
                params[param_key] = value

        return " AND ".join(clauses), params

    async def insert(self, table: str, data: Dict[str, Any]):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        sql = f"INSERT INTO {table} ({cols}) VALUES ({phs})"
        await self.driver.execute(sql, data)

    async def get(self, table: str, pk_value: Any):
        sql = f"SELECT * FROM {table} WHERE id = :pk"
        return await self.driver.fetch_one(sql, {"pk": pk_value})

    async def update(self, table: str, pk_value: Any, data: Dict[str, Any]):
        updates = ", ".join([f"{k}=:{k}" for k in data.keys()])
        sql = f"UPDATE {table} SET {updates} WHERE id = :pk"
        await self.driver.execute(sql, {**data, "pk": pk_value})

    async def upsert(self, table: str, data: Dict[str, Any]):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({phs})"
        await self.driver.execute(sql, data)

    async def delete(self, table: str, pk_value: Any):
        sql = f"DELETE FROM {table} WHERE id = :pk"
        await self.driver.execute(sql, {"pk": pk_value})

    async def get_batch(self, table: str, pk_values: List[Any]) -> List[Dict]:
        if not pk_values:
            return []
        keys = [f"pk_{i}" for i in range(len(pk_values))]
        phs = ", ".join([f":{k}" for k in keys])
        params = dict(zip(keys, pk_values))
        sql = f"SELECT * FROM {table} WHERE id IN ({phs})"
        return await self.driver.fetch_all(sql, params)

    async def find(self, table: str, filters: Dict, limit: int = -1, offset: int = 0):
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM {table} WHERE {where} ORDER BY id DESC"

        if limit > 0:
            sql += " LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset

        return await self.driver.fetch_all(sql, params)

    async def count(self, table: str, filters: Dict) -> int:
        where, params = self._build_where(filters)
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        row = await self.driver.fetch_one(sql, params)
        return row['cnt'] if row else 0

    async def update_by(self, table: str, filters: Dict, data: Dict) -> int:
        if not filters:
            raise ValueError("update_by requires filters")
        set_clauses = [f"{k}=:set_{k}" for k in data.keys()]
        set_params = {f"set_{k}": v for k, v in data.items()}
        where, where_params = self._build_where(filters)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where}"
        res = await self.driver.execute(sql, {**set_params, **where_params})
        return res.rowcount if hasattr(res, 'rowcount') else 0

    async def delete_by(self, table: str, filters: Dict) -> int:
        if not filters:
            raise ValueError("delete_by requires filters")
        where, params = self._build_where(filters)
        sql = f"DELETE FROM {table} WHERE {where}"
        res = await self.driver.execute(sql, params)
        return res.rowcount if hasattr(res, 'rowcount') else 0

    @asynccontextmanager
    async def transaction(self):
        async with self.driver.transaction():
            yield
