"""
Base Repository

Base class for data access with schema auto-registration.
Reference: pho persistence repository implementation.
"""

import json
import logging
from typing import List, Dict, Any, ClassVar, Optional, Type, Union, AsyncGenerator
from pydantic import BaseModel
from contextlib import asynccontextmanager
from .spec import TableSpec

logger = logging.getLogger("goose.persistence")


def with_table(
    name: str,
    model: Type[BaseModel],
    sql: Union[str, List[str]],
    pk: str = "id",
    priority: int = 0
):
    """
    Decorator to register a table schema.

    Args:
        name: Table name
        model: Pydantic model class
        sql: CREATE TABLE SQL statements
        pk: Primary key field
        priority: Creation priority
    """
    def wrapper(cls):
        spec = TableSpec(
            table_name=name,
            model_class=model,
            schema_sql=sql,
            pk_field=pk,
            priority=priority,
            source=cls.__name__
        )
        setattr(cls, f"TBL_{name.upper()}", spec)
        BaseRepository._registered_table_specs.append(spec)
        if not hasattr(cls, '_model_index'):
            cls._model_index = {}
        cls._model_index[model] = spec
        return cls
    return wrapper


class BaseRepository:
    """
    Base repository with auto-registration and CRUD operations.

    Features:
    - Auto-scan TableSpec attributes
    - Auto-register schemas
    - Generic CRUD methods
    - Pydantic <-> JSON serialization
    """

    _registered_table_specs: ClassVar[List[TableSpec]] = []
    _model_index: ClassVar[Dict[Type[BaseModel], TableSpec]] = {}

    def __init__(self, pm: 'PersistenceManager' = None):
        if pm is None:
            try:
                from .manager import get_persistence
                self.pm = get_persistence()
            except RuntimeError:
                self.pm = None
        else:
            self.pm = pm

    @property
    def backend(self):
        """Get the persistence backend."""
        return self.pm.backend if self.pm else None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, '_model_index'):
            cls._model_index = {}
        for _, attr in cls.__dict__.items():
            if isinstance(attr, TableSpec):
                BaseRepository._registered_table_specs.append(attr)
                BaseRepository._model_index[attr.model_class] = attr

    def _resolve_spec(self, token) -> TableSpec:
        """Resolve TableSpec from token."""
        if isinstance(token, TableSpec):
            return token
        if token in BaseRepository._model_index:
            return BaseRepository._model_index[token]
        raise ValueError(f"Spec not found for {token}")

    @classmethod
    def get_all_schemas(cls) -> List[Union[str, List[str]]]:
        """Get all registered schemas."""
        sorted_items = sorted(BaseRepository._registered_table_specs, key=lambda x: x.priority)
        return [item.schema_sql for item in sorted_items]

    def _to_db(self, model: BaseModel) -> Dict[str, Any]:
        """Convert Pydantic model to database format."""
        d = model.model_dump()
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                d[k] = json.dumps(v, ensure_ascii=False)
        return d

    def _from_db(self, row: Dict, spec: TableSpec) -> Optional[BaseModel]:
        """Convert database row to Pydantic model."""
        if not row:
            return None
        d = dict(row)
        for k, v in d.items():
            if isinstance(v, str) and v.startswith(("{", "[")):
                try:
                    d[k] = json.loads(v)
                except:
                    pass
        return spec.model_class.model_validate(d)

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """Context manager for transactions."""
        async with self.backend.transaction():
            yield

    async def _insert(self, token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        """Insert a record."""
        spec = self._resolve_spec(token)
        await self.backend.insert(spec.table_name, self._to_db(model))

    async def _get(self, token: Union[TableSpec, Type[BaseModel]], pk: Any) -> Optional[BaseModel]:
        """Get a record by primary key."""
        spec = self._resolve_spec(token)
        row = await self.backend.get(spec.table_name, pk)
        return self._from_db(row, spec)

    async def _get_batch(
        self,
        token: Union[TableSpec, Type[BaseModel]],
        pks: List[Any]
    ) -> List[BaseModel]:
        """Batch get records by primary keys."""
        spec = self._resolve_spec(token)
        rows = await self.backend.get_batch(spec.table_name, pks)
        return [self._from_db(r, spec) for r in rows]

    async def _find(
        self,
        token: Union[TableSpec, Type[BaseModel]],
        filters: Dict,
        limit: int = -1,
        offset: int = 0
    ) -> List[BaseModel]:
        """Find records by filters."""
        spec = self._resolve_spec(token)
        rows = await self.backend.find(spec.table_name, filters, limit=limit, offset=offset)
        return [self._from_db(r, spec) for r in rows]

    async def _count(self, token: Union[TableSpec, Type[BaseModel]], filters: Dict) -> int:
        """Count records by filters."""
        spec = self._resolve_spec(token)
        return await self.backend.count(spec.table_name, filters)

    async def _update_by(
        self,
        token: Union[TableSpec, Type[BaseModel]],
        filters: Dict,
        **kwargs
    ) -> int:
        """Update records by filters."""
        spec = self._resolve_spec(token)
        return await self.backend.update_by(spec.table_name, filters, kwargs)

    async def _delete_by(self, token: Union[TableSpec, Type[BaseModel]], filters: Dict) -> int:
        """Delete records by filters."""
        spec = self._resolve_spec(token)
        return await self.backend.delete_by(spec.table_name, filters)

    async def _upsert(self, token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        """Insert or update a record."""
        spec = self._resolve_spec(token)
        await self.backend.upsert(spec.table_name, self._to_db(model))
