import json
import os
import asyncio
import aiofiles
from typing import Any, Dict, List
from contextlib import asynccontextmanager
from ..backend import PersistenceBackend
from ..spec import TableSpec

class JsonlBackend(PersistenceBackend):
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self._lock = asyncio.Lock()

    def _get_path(self, table): return os.path.join(self.data_dir, f"{table}.jsonl")
    
    async def _read(self, path) -> List[Dict]:
        if not os.path.exists(path): return []
        async with aiofiles.open(path, 'r') as f:
            lines = await f.readlines()
            return [json.loads(l) for l in lines if l.strip()]

    async def _write(self, path, rows):
        async with aiofiles.open(path, 'w') as f:
            for r in rows:
                await f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _matches(self, row: Dict, filters: Dict) -> bool:
        """增强版内存匹配器"""
        for field, condition in filters.items():
            row_val = row.get(field)
            
            # 场景 A: 复杂条件 (字典且带 $)
            if isinstance(condition, dict) and any(k.startswith("$") for k in condition.keys()):
                for op, op_val in condition.items():
                    if not self._check_op(row_val, op, op_val):
                        return False
            
            # 场景 B: 简单相等
            else:
                if row_val != condition:
                    return False
        return True

    def _check_op(self, value: Any, op: str, target: Any) -> bool:
        """执行具体的操作符逻辑"""
        # 处理 None 的情况
        if value is None:
            return False # 简单处理：None 不参与比较 (除了 is None，这里暂不实现)

        try:
            if op == "$eq": return value == target
            if op == "$ne": return value != target
            if op == "$gt": return value > target
            if op == "$gte": return value >= target
            if op == "$lt": return value < target
            if op == "$lte": return value <= target
            if op == "$in": return value in target
            if op == "$nin": return value not in target
            
            if op == "$like": 
                # 简单的内存 LIKE 模拟
                # SQL: %keyword% -> Python: keyword in value
                # SQL: keyword%  -> Python: value.startswith(keyword)
                pattern = str(target).replace("%", "")
                return pattern in str(value)
            
            if op == "$ilike":
                return str(target).replace("%", "").lower() in str(value).lower()
                
        except TypeError:
            # 防止类型不匹配比较报错 (如 int vs str)
            return False
            
        return False
    
    async def boot(self, schemas): os.makedirs(self.data_dir, exist_ok=True)

    # --- 实现 ---
    async def insert(self, spec, data):
        async with self._lock:
            async with aiofiles.open(self._get_path(spec.table_name), 'a') as f:
                await f.write(json.dumps(data, ensure_ascii=False) + "\n")

    async def get(self, spec, pk):
        rows = await self._read(self._get_path(spec.table_name))
        pk_str = str(pk)
        for r in reversed(rows):
            if str(r.get(spec.pk_field)) == pk_str: return r
        return None

    async def get_batch(self, spec, pk_values):
        rows = await self._read(self._get_path(spec.table_name))
        ids = set(str(k) for k in pk_values)
        return [r for r in rows if str(r.get(spec.pk_field)) in ids]

    async def find(self, spec, filters, limit=-1, offset=0):
        rows = await self._read(self._get_path(spec.table_name))
        matched = [r for r in rows if self._matches(r, filters)]
        matched.reverse()
        if limit > 0:
            return matched[offset : offset + limit]
        else:
            return matched[offset:]

    async def count(self, spec, filters):
        rows = await self._read(self._get_path(spec.table_name))
        return sum(1 for r in rows if self._matches(r, filters))

    async def update(self, spec, pk, data):
        path = self._get_path(spec.table_name)
        async with self._lock:
            rows = await self._read(path)
            updated = False
            for r in rows:
                if str(r.get(spec.pk_field)) == str(pk):
                    r.update(data)
                    updated = True
            if updated: await self._write(path, rows)

    async def update_by(self, spec, filters, data):
        path = self._get_path(spec.table_name)
        async with self._lock:
            rows = await self._read(path)
            count = 0
            for r in rows:
                if self._matches(r, filters):
                    r.update(data)
                    count += 1
            if count: await self._write(path, rows)
            return count

    async def upsert(self, spec, data):
        pk = data.get(spec.pk_field)
        existing = await self.get(spec, pk)
        if existing: await self.update(spec, pk, data)
        else: await self.insert(spec, data)

    async def delete(self, spec, pk):
        await self.delete_by(spec, {spec.pk_field: pk})

    async def delete_by(self, spec, filters):
        path = self._get_path(spec.table_name)
        async with self._lock:
            rows = await self._read(path)
            new_rows = [r for r in rows if not self._matches(r, filters)]
            count = len(rows) - len(new_rows)
            if count: await self._write(path, new_rows)
            return count

    @asynccontextmanager
    async def transaction(self):
        async with self._lock: yield