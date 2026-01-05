# src/goose/persistence/spec.py
from dataclasses import dataclass
from typing import Type, Any
from pydantic import BaseModel

@dataclass
class TableSpec:
    """
    [Explicit] Explicitly defines database table metadata.
    """
    table_name: str
    model_class: Type[BaseModel]
    schema_sql: str
    pk_field: str = "id"
    priority: int = 0  # Table creation priority (0=first, 10=dependent tables)

    def __post_init__(self):
        # Simple SQL preprocessing
        self.schema_sql = self.schema_sql.strip()