# src/goose/persistence/repository.py

import json
import logging
from typing import List, Dict, Any, ClassVar, Optional,Type,TYPE_CHECKING,Union,AsyncGenerator
from pydantic import BaseModel
from contextlib import asynccontextmanager
from .spec import TableSpec
if TYPE_CHECKING:
    from .manager import PersistenceManager
from datetime import datetime

logger = logging.getLogger("goose.persistence")

def with_table(
    name: str,
    model: Type[BaseModel],
    sql: Union[str, List[str]],
    pk: str = "id",
    priority: int = 0,
    attr_name: str = None
):
    """
    [Decorator] 为 Repository 注册一张表
    
    :param name: 数据库表名
    :param model: Pydantic 模型类
    :param sql: 建表 SQL
    :param pk: 主键字段名
    :param priority: 建表优先级
    :param attr_name: (可选) 注入到类的属性名，默认自动生成为 TBL_{大写表名}
    """
    def wrapper(cls):
        # 1. 创建 Spec 对象
        spec = TableSpec(
            table_name=name,
            model_class=model,
            schema_sql=sql,
            pk_field=pk,
            priority=priority,
            source=cls.__name__
        )

        # 2. 自动注入属性 (方便 self._get(self.TBL_XXX) 调用)
        # 如果未指定 attr_name，则默认为 TBL_表名 (例如: TBL_EXECUTIONS)
        inject_name = attr_name or f"TBL_{name.upper()}"
        
        # 防止覆盖已存在的属性
        if hasattr(cls, inject_name):
            raise ValueError(f"Attribute {inject_name} already exists in {cls.__name__}")
        
        setattr(cls, inject_name, spec)

        # 3. 注册到 BaseRepository 的全局注册表
        # 注意：这里我们直接操作 BaseRepository 的类属性
        BaseRepository._registered_table_specs.append(spec)
        if not hasattr(cls, '_model_index'): cls._model_index = {}
        cls._model_index[model] = spec
        
        return cls
    return wrapper

class BaseRepository:
    """
    [Core] 支持属性自省 (Introspection) 的 Repository 基类
    
    特性：
    1. 自动扫描子类中定义的 TableSpec 属性。
    2. 自动注册 Schema 到全局注册表。
    3. 提供基于 TableSpec 的通用 CRUD 方法 (_get, _insert, _update...)。
    4. 自动处理 Pydantic <-> JSON (SQLite) 的序列化转换。
    """
    
    # 全局 Schema 注册表 (单例)
    # 结构: [{"sql": "...", "priority": 0, "source": "RepoName", "table": "table_name"}]
    _registered_table_specs: ClassVar[List[TableSpec]] = []
    _model_index: ClassVar[Dict[Type[BaseModel], TableSpec]] = {}
    
    def __init__(self, pm:'PersistenceManager' = None):
        # 如果没传 pm，就尝试获取全局单例
        if pm is None:
            try:
                from .manager import get_persistence
                self.pm = get_persistence()
            except RuntimeError:
                # 允许在单元测试中不初始化单例，只要手动传入 pm 即可
                self.pm = None 
        else:
            self.pm = pm
        
    @property
    def backend(self):
        return self.pm.backend
    # ==========================================
    # 1. 核心：属性自省与自动注册
    # ==========================================
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        if not hasattr(cls, '_model_index'): cls._model_index = {}
        
        for _, attr in cls.__dict__.items():
            if isinstance(attr, TableSpec):
                BaseRepository._registered_table_specs.append(attr)
                BaseRepository._model_index[attr.model_class] = attr
                
    def _resolve_spec(self, token):
        if isinstance(token, TableSpec): return token
        if token in BaseRepository._model_index: return BaseRepository._model_index[token]
        raise ValueError(f"Spec not found for {token}")
    
    @classmethod
    def get_all_schemas(cls) -> List[str|list[str]]:
        """供 PersistenceManager.boot() 调用"""
        # 按优先级升序排序 (0 -> 10 -> 100)
        sorted_items = sorted(BaseRepository._registered_table_specs, key=lambda x: x.priority)
        return [item.schema_sql for item in sorted_items]

    
    # --- Data Mapper ---
    def _to_db(self, model: BaseModel):
        d = model.model_dump()
        for k, v in d.items():
            if isinstance(v, (dict, list)): d[k] = json.dumps(v, ensure_ascii=False)
        return d

    def _from_db(self, row, spec:TableSpec):
        if not row: return None
        d = dict(row)
        for k, v in d.items():
            if isinstance(v, str) and v.startswith(("{", "[")):
                try: d[k] = json.loads(v)
                except: pass
        return spec.model_class.model_validate(d)
    

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """
        开启一个事务上下文。
        对于 SQL 后端，这是真正的 DB 事务；
        对于 JSONL 后端，这是文件锁。
        """
        async with self.backend.transaction():
            yield
            
   # --- Public Helper Methods ---
    
    async def _insert(self, token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        spec = self._resolve_spec(token)
        await self.backend.insert(spec, self._to_db(model))

    async def _get(self, token: Union[TableSpec, Type[BaseModel]], pk: Any) -> BaseModel:
        spec = self._resolve_spec(token)
        row = await self.backend.get(spec, pk)
        return self._from_db(row, spec)

    async def _get_batch(self, token, pks: List[Any]) -> List[BaseModel]:
        spec = self._resolve_spec(token)
        rows = await self.backend.get_batch(spec, pks)
        return [self._from_db(r, spec) for r in rows]

    async def _find(self, token, filters: Dict, limit=-1,offset=0) -> List[BaseModel]:
        """根据过滤条件查询: 
        await _find(User, {"status": "active"})
        # 1. 基础写法 (默认相等)
        filters = {"status": "running"}

        # 2. 复杂写法 (使用操作符)
        filters = {
            "age": {"$gt": 18},              # age > 18
            "score": {"$gte": 60, "$lt": 90},# 60 <= score < 90
            "role": {"$in": ["admin", "dev"]}, # role IN ('admin', 'dev')
            "name": {"$like": "%Goose%"}     # name LIKE '%Goose%'
        }
        """
        spec = self._resolve_spec(token)
        rows = await self.backend.find(spec, filters, limit=limit,offset=offset)
        return [self._from_db(r, spec) for r in rows]
    
    async def _count(self, token, filters: Dict) -> int:
        """
        根据过滤条件查询数量: await _count(User, {"status": "active"})
        # 1. 基础写法 (默认相等)
        filters = {"status": "running"}

        # 2. 复杂写法 (使用操作符)
        filters = {
            "age": {"$gt": 18},              # age > 18
            "score": {"$gte": 60, "$lt": 90},# 60 <= score < 90
            "role": {"$in": ["admin", "dev"]}, # role IN ('admin', 'dev')
            "name": {"$like": "%Goose%"}     # name LIKE '%Goose%'
        }
        """
        spec = self._resolve_spec(token)
        return await self.backend.count(spec, filters)

    async def _update_by(self, token, filters: Dict, **kwargs) -> int:
        """批量更新: await _update_by(User, {"role": "guest"}, status="inactive")
        # 1. 基础写法 (默认相等)
        filters = {"status": "running"}

        # 2. 复杂写法 (使用操作符)
        filters = {
            "age": {"$gt": 18},              # age > 18
            "score": {"$gte": 60, "$lt": 90},# 60 <= score < 90
            "role": {"$in": ["admin", "dev"]}, # role IN ('admin', 'dev')
            "name": {"$like": "%Goose%"}     # name LIKE '%Goose%'
        }
        """
        spec = self._resolve_spec(token)
        return await self.backend.update_by(spec, filters, kwargs)

    async def _delete_by(self, token, filters: Dict) -> int:
        spec = self._resolve_spec(token)
        return await self.backend.delete_by(spec, filters)
        
    async def _upsert(self, token, model: BaseModel):
        spec = self._resolve_spec(token)
        await self.backend.upsert(spec, self._to_db(model))
    
    