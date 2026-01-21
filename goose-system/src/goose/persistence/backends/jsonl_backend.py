"""
JSONL Backend

JSON Lines file-based backend implementation.
Reference: pho persistence JSONL backend.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from ..backend import PersistenceBackend

logger = logging.getLogger("goose.persistence.jsonl")


class JSONLBackend(PersistenceBackend):
    """
    JSONL file-based backend.

    Stores each record as a JSON object per line.
    Simple, file-based storage without external dependencies.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._tables: Dict[str, Path] = {}

    def _get_table_path(self, table: str) -> Path:
        """Get path for table file."""
        if table not in self._tables:
            self._tables[table] = self.data_dir / f"{table}.jsonl"
        return self._tables[table]

    async def boot(self, schemas: List[Dict]) -> None:
        """Initialize by creating table files."""
        for table in set(self._tables.keys()):
            path = self._get_table_path(table)
            if not path.exists():
                path.touch()
        logger.info(f"JSONL backend initialized at {self.data_dir}")

    async def close(self) -> None:
        """No-op for file-based storage."""
        pass

    async def insert(self, table: str, data: Dict[str, Any]):
        path = self._get_table_path(table)
        line = json.dumps(data, ensure_ascii=False)
        async with aiofiles.open(path, 'a', encoding='utf-8') as f:
            await f.write(line + '\n')

    async def get(self, table: str, pk_value: Any) -> Optional[Dict]:
        path = self._get_table_path(table)
        if not path.exists():
            return None
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if record.get('id') == pk_value:
                    return record
        return None

    async def update(self, table: str, pk_value: Any, data: Dict[str, Any]):
        path = self._get_table_path(table)
        if not path.exists():
            return

        updated = False
        records = []
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if record.get('id') == pk_value:
                    record.update(data)
                    updated = True
                records.append(record)

        if updated:
            async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                for record in records:
                    await f.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def upsert(self, table: str, data: Dict[str, Any]):
        path = self._get_table_path(table)
        pk = data.get('id')

        records = []
        upserted = False
        if path.exists():
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                async for line in f:
                    record = json.loads(line)
                    if record.get('id') == pk:
                        record.update(data)
                        upserted = True
                    records.append(record)

        if not upserted:
            records.append(data)

        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            for record in records:
                await f.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def delete(self, table: str, pk_value: Any):
        path = self._get_table_path(table)
        if not path.exists():
            return

        records = []
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if record.get('id') != pk_value:
                    records.append(record)

        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            for record in records:
                await f.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def get_batch(self, table: str, pk_values: List[Any]) -> List[Dict]:
        path = self._get_table_path(table)
        pk_set = set(pk_values)
        results = []

        if not path.exists():
            return results

        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if record.get('id') in pk_set:
                    results.append(record)

        return results

    async def find(
        self,
        table: str,
        filters: Dict[str, Any],
        limit: int = -1,
        offset: int = 0
    ) -> List[Dict]:
        path = self._get_table_path(table)
        results = []

        if not path.exists():
            return results

        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if self._matches(record, filters):
                    results.append(record)

        return results[offset:offset + limit if limit > 0 else None]

    def _matches(self, record: Dict, filters: Dict) -> bool:
        """Check if record matches filters."""
        for field, value in filters.items():
            if isinstance(value, dict):
                for op, op_val in value.items():
                    if op == "$eq" and record.get(field) != op_val:
                        return False
                    elif op == "$ne" and record.get(field) == op_val:
                        return False
                    elif op == "$gt" and record.get(field, 0) <= op_val:
                        return False
                    elif op == "$gte" and record.get(field, 0) < op_val:
                        return False
                    elif op == "$lt" and record.get(field, 0) >= op_val:
                        return False
                    elif op == "$lte" and record.get(field, 0) > op_val:
                        return False
                    elif op == "$in" and record.get(field) not in op_val:
                        return False
                    elif op == "$like" and op_val not in record.get(field, ""):
                        return False
            elif record.get(field) != value:
                return False
        return True

    async def count(self, table: str, filters: Dict[str, Any]) -> int:
        results = await self.find(table, filters)
        return len(results)

    async def update_by(self, table: str, filters: Dict[str, Any], data: Dict[str, Any]) -> int:
        path = self._get_table_path(table)
        if not path.exists():
            return 0

        updated_count = 0
        records = []
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if self._matches(record, filters):
                    record.update(data)
                    updated_count += 1
                records.append(record)

        if updated_count > 0:
            async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                for record in records:
                    await f.write(json.dumps(record, ensure_ascii=False) + '\n')

        return updated_count

    async def delete_by(self, table: str, filters: Dict[str, Any]) -> int:
        path = self._get_table_path(table)
        if not path.exists():
            return 0

        deleted_count = 0
        records = []
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            async for line in f:
                record = json.loads(line)
                if self._matches(record, filters):
                    deleted_count += 1
                else:
                    records.append(record)

        if deleted_count > 0:
            async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                for record in records:
                    await f.write(json.dumps(record, ensure_ascii=False) + '\n')

        return deleted_count

    @asynccontextmanager
    async def transaction(self):
        yield


try:
    import aiofiles
except ImportError:
    aiofiles = None
