# src/goose/persistence/spec.py
from dataclasses import dataclass
from typing import Type, Any, Union, List,Optional
from pydantic import BaseModel

@dataclass
class TableSpec:
    """
    [Explicit] Explicitly defines database table metadata.
    """
    table_name: str
    model_class: Type[BaseModel]
    schema_sql: Union[str, List[str]]
    pk_field: str = "id"
    priority: int = 0  # Table creation priority (0=first, 10=dependent tables)
    source: Optional[str] = None
    
    def __post_init__(self):
        # 1. 如果传入的是单字符串，先 strip，再转为 List（统一格式）
        if isinstance(self.schema_sql, str):
            # 简单的处理：如果包含分号，可能用户在一个字符串里写了多条语句
            # 但为了安全起见，我们把它当做一个元素
            self.schema_sql = [self.schema_sql.strip()]
        
        # 2. 如果已经是 List，则处理每一项
        elif isinstance(self.schema_sql, list):
            self.schema_sql = [sql.strip() for sql in self.schema_sql if sql.strip()]