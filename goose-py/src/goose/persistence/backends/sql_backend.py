from typing import Any, Dict, List, Tuple
from ..backend import PersistenceBackend
from ..spec import TableSpec
from ..drivers.base import SQLDriver
from ..drivers.sqlalchemy_driver import SQLAlchemyDriver
from contextlib import asynccontextmanager

class SQLBackend(PersistenceBackend):
    """
    [Adapter] 将 Spec/Dict 翻译为 SQL 语句，委托 Driver 执行
    """
    def __init__(self, db_url: str):
        # 默认注入 SQLAlchemyDriver，也可以通过工厂注入其他
        self.driver: SQLDriver = SQLAlchemyDriver(db_url)

    async def boot(self, schemas: list):
        await self.driver.connect()
        for item in schemas:
            try:
                await self.driver.execute(item['sql'])
            except Exception:
                pass # 忽略已存在错误

    def _build_where(self, filters: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        构建 WHERE 子句和参数
        :param filters: 过滤条件字典
        :return: WHERE 子句和参数字典
        """
        if not filters: return "1=1", {}
        clauses = []
        params = {}
        # 避免参数名冲突的计数器
        param_idx = 0 

        for field, value in filters.items():
            # 场景 A: value 是字典，包含操作符 (e.g., {"$gt": 18})
            if isinstance(value, dict) and any(k.startswith("$") for k in value.keys()):
                for op, op_val in value.items():
                    param_key = f"p_{param_idx}_{field}"  # 生成唯一参数名
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
                    elif op == "$ilike": # Postgres 特有忽略大小写
                        clauses.append(f"{field} ILIKE :{param_key}")
                    elif op == "$in":
                        # SQL 的 IN 需要特殊处理参数展开
                        # 这里简单处理：假设 driver 支持 tuple/list 传参 (如 sqlalchemy/databases)
                        # 如果底层是原生 sqlite3，这里需要手动展开
                        clauses.append(f"{field} IN :{param_key}")
                    else:
                        raise ValueError(f"Unknown operator: {op}")
                    
                    params[param_key] = op_val

            # 场景 B: value 是直接值 (默认等于)
            else:
                param_key = f"p_{param_idx}_{field}"
                param_idx += 1
                clauses.append(f"{field} = :{param_key}")
                params[param_key] = value

        return " AND ".join(clauses), params

    # --- 实现 ---

    async def insert(self, spec: TableSpec, data: Dict):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        sql = f"INSERT INTO {spec.table_name} ({cols}) VALUES ({phs})"
        await self.driver.execute(sql, data)

    async def get(self, spec: TableSpec, pk_value: Any):
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        return await self.driver.fetch_one(sql, {"pk": pk_value})

    async def get_batch(self, spec: TableSpec, pk_values: List[Any]):
        if not pk_values: return []
        # 手动展开 IN 查询
        keys = [f"pk_{i}" for i in range(len(pk_values))]
        phs = ", ".join([f":{k}" for k in keys])
        params = dict(zip(keys, pk_values))
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} IN ({phs})"
        return await self.driver.fetch_all(sql, params)

    async def find(self, spec: TableSpec, filters: Dict, limit=-1, offset=0):
        where, params = self._build_where(filters)
        # 动态构建 SQL
        sql = f"SELECT * FROM {spec.table_name} WHERE {where} ORDER BY {spec.pk_field} DESC"
        
        # 只有当 limit > 0 时才加 LIMIT 子句
        if limit > 0:
            sql += " LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset
        return await self.driver.fetch_all(sql, {**params, "limit": limit, "offset": offset})

    async def count(self, spec: TableSpec, filters: Dict):
        where, params = self._build_where(filters)
        sql = f"SELECT COUNT(*) as cnt FROM {spec.table_name} WHERE {where}"
        row = await self.driver.fetch_one(sql, params)
        return row['cnt'] if row else 0

    async def update(self, spec: TableSpec, pk_value: Any, data: Dict):
        updates = ", ".join([f"{k}=:{k}" for k in data.keys() if k != spec.pk_field])
        sql = f"UPDATE {spec.table_name} SET {updates} WHERE {spec.pk_field} = :{spec.pk_field}"
        await self.driver.execute(sql, {**data, spec.pk_field: pk_value})

    async def update_by(self, spec: TableSpec, filters: Dict, data: Dict):
        if not filters: raise ValueError("update_by requires filters")
        # 分离 SET 和 WHERE 参数
        set_clauses = [f"{k}=:set_{k}" for k in data.keys() if k != spec.pk_field]
        set_params = {f"set_{k}": v for k, v in data.items() if k != spec.pk_field}
        
        where, where_params = self._build_where(filters)
        
        sql = f"UPDATE {spec.table_name} SET {', '.join(set_clauses)} WHERE {where}"
        res = await self.driver.execute(sql, {**set_params, **where_params})
        return res.rowcount

    async def upsert(self, spec: TableSpec, data: Dict):
        cols = ", ".join(data.keys())
        phs = ", ".join([f":{k}" for k in data.keys()])
        # SQLite 语法，PG需调整
        sql = f"INSERT OR REPLACE INTO {spec.table_name} ({cols}) VALUES ({phs})"
        await self.driver.execute(sql, data)

    async def delete(self, spec: TableSpec, pk_value: Any):
        sql = f"DELETE FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        await self.driver.execute(sql, {"pk": pk_value})

    async def delete_by(self, spec: TableSpec, filters: Dict):
        if not filters: raise ValueError("delete_by requires filters")
        where, params = self._build_where(filters)
        sql = f"DELETE FROM {spec.table_name} WHERE {where}"
        res = await self.driver.execute(sql, params)
        return res.rowcount

    @asynccontextmanager
    async def transaction(self):
        async with self.driver.transaction():
            yield