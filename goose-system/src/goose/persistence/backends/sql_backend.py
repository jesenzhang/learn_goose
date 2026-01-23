"""
SQL Backend

SQL database backend implementation using drivers.
Reference: pho persistence SQL backend.
"""

import logging
from typing import Any, Dict, List, Tuple, Optional, Union
from contextlib import asynccontextmanager

from ..backend import PersistenceBackend
from ..spec import TableSpec
from ..drivers import SQLAlchemyDriver

logger = logging.getLogger("goose.persistence.sql")

class SQLBackend(PersistenceBackend):
    """
    SQL backend adapter using SQLAlchemy driver.

    Supports SQLite, PostgreSQL, MySQL through SQLAlchemy.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.driver = SQLAlchemyDriver(db_url)

    async def boot(self, schemas: List[Union[str, List[str]]]) -> None:
        await self.driver.connect()
        for item in schemas:
            try:
                sql_list = []
                if isinstance(item, str):
                    sql_list = [item.strip()]
                elif isinstance(item, list):
                    sql_list = [s.strip() for s in item if s.strip()]
                
                for sql in sql_list:
                    if ";" in sql and not sql.strip().endswith(";"):
                        pass
                    await self.driver.execute(sql)
                    
            except Exception as e:
                logger.error(f"Failed to init table: {e}")

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

    async def insert(self, spec: TableSpec, data: Dict[str, Any]):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        sql = f"INSERT INTO {spec.table_name} ({cols}) VALUES ({phs})"
        await self.driver.execute(sql, data)

    async def get(self, spec: TableSpec, pk_value: Any) -> Optional[Dict]:
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        return await self.driver.fetch_one(sql, {"pk": pk_value})

    async def update(self, spec: TableSpec, pk_value: Any, data: Dict[str, Any]):
        updates = ", ".join([f"{k}=:{k}" for k in data.keys()])
        sql = f"UPDATE {spec.table_name} SET {updates} WHERE {spec.pk_field} = :pk"
        await self.driver.execute(sql, {**data, "pk": pk_value})

    async def upsert(self, spec: TableSpec, data: Dict[str, Any]):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        if "sqlite" in self.db_url:
            sql = f"INSERT OR REPLACE INTO {spec.table_name} ({cols}) VALUES ({phs})"
        else:
            sql = f"INSERT INTO {spec.table_name} ({cols}) VALUES ({phs}) ON CONFLICT({spec.pk_field}) DO UPDATE SET {', '.join([f'{k}=:{k}' for k in data.keys()])}"
        await self.driver.execute(sql, data)

    async def delete(self, spec: TableSpec, pk_value: Any):
        sql = f"DELETE FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        await self.driver.execute(sql, {"pk": pk_value})

    async def get_batch(self, spec: TableSpec, pk_values: List[Any]) -> List[Dict]:
        if not pk_values:
            return []
        keys = [f"pk_{i}" for i in range(len(pk_values))]
        phs = ", ".join([f":{k}" for k in keys])
        params = dict(zip(keys, pk_values))
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} IN ({phs})"
        return await self.driver.fetch_all(sql, params)

    async def find(self, spec: TableSpec, filters: Dict, limit: int = -1, offset: int = 0):
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM {spec.table_name} WHERE {where} ORDER BY {spec.pk_field} DESC"

        if limit > 0:
            sql += " LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset

        return await self.driver.fetch_all(sql, params)

    async def count(self, spec: TableSpec, filters: Dict) -> int:
        where, params = self._build_where(filters)
        sql = f"SELECT COUNT(*) as cnt FROM {spec.table_name} WHERE {where}"
        row = await self.driver.fetch_one(sql, params)
        return row['cnt'] if row else 0

    async def update_by(self, spec: TableSpec, filters: Dict, data: Dict) -> int:
        if not filters:
            raise ValueError("update_by requires filters")
        set_clauses = [f"{k}=:set_{k}" for k in data.keys()]
        set_params = {f"set_{k}": v for k, v in data.items()}
        where, where_params = self._build_where(filters)
        sql = f"UPDATE {spec.table_name} SET {', '.join(set_clauses)} WHERE {where}"
        res = await self.driver.execute(sql, {**set_params, **where_params})
        return res.rowcount if hasattr(res, 'rowcount') else 0

    async def delete_by(self, spec: TableSpec, filters: Dict) -> int:
        if not filters:
            raise ValueError("delete_by requires filters")
        where, params = self._build_where(filters)
        sql = f"DELETE FROM {spec.table_name} WHERE {where}"
        res = await self.driver.execute(sql, params)
        return res.rowcount if hasattr(res, 'rowcount') else 0

    @asynccontextmanager
    async def transaction(self):
        async with self.driver.transaction():
            yield
