# src/goose/persistence/repository.py

import json
import logging
from typing import List, Dict, Any, ClassVar, Optional,Type,TYPE_CHECKING,Union
from pydantic import BaseModel
from .spec import TableSpec

if TYPE_CHECKING:
    from goose.persistence.manager import PersistenceManager
    
logger = logging.getLogger("goose.persistence")

def with_table(
    name: str,
    model: Type[BaseModel],
    sql: str,
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
            priority=priority
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
        BaseRepository._registered_schemas.append({
            "sql": spec.schema_sql,
            "priority": spec.priority,
            "table": spec.table_name,
            "source": cls.__name__
        })
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
    _registered_schemas: ClassVar[List[Dict[str, Any]]] = []
    _model_index: ClassVar[Dict[Type[BaseModel], TableSpec]] = {}
    
    def __init__(self, pm:'PersistenceManager' = None):
        if pm is None:
            from goose.persistence.manager import persistence_manager
            pm = persistence_manager
        self.pm = pm

    # ==========================================
    # 1. 核心：属性自省与自动注册
    # ==========================================
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # 🔍 扫描子类的 __dict__，寻找 TableSpec 类型的属性
        found_specs = []
        for attr_name, attr_value in cls.__dict__.items():
            if isinstance(attr_value, TableSpec):
                found_specs.append(attr_value)
                logger.debug(f"🔎 Found table spec '{attr_value.table_name}' in {cls.__name__}")

        cls._model_index = {}
        
        # 📦 注册到 BaseRepository 的全局列表
        # 注意：显式使用 BaseRepository 防止多文件导入导致的类分裂问题
        for spec in found_specs:
            BaseRepository._registered_schemas.append({
                "sql": spec.schema_sql,
                "priority": spec.priority,
                "table": spec.table_name,
                "source": cls.__name__
            })
            cls._model_index[spec.model_class] = spec
                
    def _get_spec(self, token: Union[TableSpec, Type[BaseModel]]) -> TableSpec:
        """核心路由：既支持传 Spec 对象，也支持传 Model 类"""
        if isinstance(token, TableSpec):
            return token
        
        # 如果传的是 Model 类，查表
        if token in self._model_index:
            return self._model_index[token]
            
        raise ValueError(f"No table registered for model {token}")
    
    @classmethod
    def get_all_schemas(cls) -> List[str]:
        """供 PersistenceManager.boot() 调用"""
        # 按优先级升序排序 (0 -> 10 -> 100)
        sorted_items = sorted(BaseRepository._registered_schemas, key=lambda x: x['priority'])
        return [item['sql'] for item in sorted_items]

    
    # ==========================================
    # Generic CRUD Helpers (Private Helpers)
    # Now CRUD operations require passing 'spec' to specify the table
    # ==========================================

    def _to_db_params(self, model: BaseModel) -> Dict[str, Any]:
        """JSON Serialization Helper"""
        data = model.model_dump()
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                data[k] = json.dumps(v, ensure_ascii=False)
        return data
    
    def _from_db_row(self, row: Any, spec: TableSpec) -> Optional[BaseModel]:
        """
        DB Row -> Pydantic
        自动将 JSON 字符串转回 dict/list
        """
        if not row:
            return None
        
        row_dict = dict(row)
        
        # 尝试智能解析 JSON 字符串
        # 这一步是为了应对 SQLite 返回的是字符串而不是原生 JSON 类型
        for k, v in row_dict.items():
            if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
                try:
                    row_dict[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass # 解析失败则保留原字符串
        
        return spec.model_class.model_validate(row_dict)

    # ==========================================
    # 3. 通用 CRUD (Private Helpers)
    # 业务层通过 self.spec_attr 调用这些方法
    # ==========================================

    async def _insert(self,token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        spec = self._get_spec(token)
        data = self._to_db_params(model)
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f":{k}" for k in data.keys()])
        
        sql = f"INSERT INTO {spec.table_name} ({cols}) VALUES ({placeholders})"
        await self.pm.execute(sql, data)

    async def _upsert(self, token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        """SQLite specific: INSERT OR REPLACE"""
        spec = self._get_spec(token)
        data = self._to_db_params(model)
        cols = ", ".join(data.keys())
        placeholders = ", ".join([f":{k}" for k in data.keys()])
        
        sql = f"INSERT OR REPLACE INTO {spec.table_name} ({cols}) VALUES ({placeholders})"
        await self.pm.execute(sql, data)

    async def _update(self, token: Union[TableSpec, Type[BaseModel]], model: BaseModel):
        spec = self._get_spec(token)
        data = self._to_db_params(model)
        pk = data.get(spec.pk_field)
        if pk is None:
            raise ValueError(f"PK {spec.pk_field} missing for update")
        
        # 排除 PK 字段的更新
        updates = ", ".join([f"{k}=:{k}" for k in data.keys() if k != spec.pk_field])
        sql = f"UPDATE {spec.table_name} SET {updates} WHERE {spec.pk_field}=:{spec.pk_field}"
        await self.pm.execute(sql, data)

    async def _get(self, token: Union[TableSpec, Type[BaseModel]], pk_value: Any) -> Optional[BaseModel]:
        spec = self._get_spec(token)
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        row = await self.pm.fetch_one(sql, {"pk": pk_value})
        return self._from_db_row(row, spec)

    async def _get_batch(self, token: Union[TableSpec, Type[BaseModel]], pk_values: List[Any]) -> List[Optional[BaseModel]]:
        spec = self._get_spec(token)
        sql = f"SELECT * FROM {spec.table_name} WHERE {spec.pk_field} IN ({', '.join([f':{k}' for k in pk_values])})"
        rows = await self.pm.fetch_all(sql, {"pk": pk_values})
        return [self._from_db_row(row, spec) for row in rows]
    
    async def _delete(self, token: Union[TableSpec, Type[BaseModel]], pk_value: Any):
        spec = self._get_spec(token)
        sql = f"DELETE FROM {spec.table_name} WHERE {spec.pk_field} = :pk"
        await self.pm.execute(sql, {"pk": pk_value})
    

    async def _list(self, token: Union[TableSpec, Type[BaseModel]], sort_key: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[BaseModel]:
        """分页列表"""
        spec = self._get_spec(token)
        pk_field = spec.pk_field if sort_key is None else sort_key
        sql = f"SELECT * FROM {spec.table_name} ORDER BY {pk_field} DESC LIMIT :limit OFFSET :offset"  # Fixed typo here
        rows = await self.pm.fetch_all(sql, {"limit": limit, "offset": offset})
        return [self._from_db_row(r, spec) for r in rows if r]
