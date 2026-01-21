"""
Table Specification

Defines table schema and metadata for persistence.
Reference: pho persistence spec implementation.
"""

from dataclasses import dataclass
from typing import Type, Any, Union, List, Optional
from pydantic import BaseModel


@dataclass
class TableSpec:
    """
    Defines table schema and metadata.

    Attributes:
        table_name: Database table name
        model_class: Pydantic model class
        schema_sql: SQL schema statements
        pk_field: Primary key field name
        priority: Creation priority (0=first)
        source: Source class name
    """
    table_name: str
    model_class: Type[BaseModel]
    schema_sql: Union[str, List[str]]
    pk_field: str = "id"
    priority: int = 0
    source: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.schema_sql, str):
            self.schema_sql = [self.schema_sql.strip()]
        elif isinstance(self.schema_sql, list):
            self.schema_sql = [sql.strip() for sql in self.schema_sql if sql.strip()]


@dataclass
class FieldSpec:
    """Field specification."""
    name: str
    type: str
    primary_key: bool = False
    nullable: bool = True
    default: Any = None
