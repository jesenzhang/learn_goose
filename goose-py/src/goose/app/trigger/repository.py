# src/goose/server/repositories.py
import json
import logging

from goose.persistence import persistence_manager
from .types import TriggerDefinition
from typing import List

logger = logging.getLogger("goose.app.trigger.repo")

TRIGGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id TEXT PRIMARY KEY,
    type TEXT,
    workflow_id TEXT,
    enabled BOOLEAN,
    config TEXT,        -- JSON
    input_mapping TEXT, -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

class TriggerRepository:
    def __init__(self):
        self.pm = persistence_manager
        self.pm.register_schema(TRIGGER_SCHEMA)

    async def list_active(self) -> List[TriggerDefinition]:
        """加载所有启用的触发器"""
        sql = "SELECT * FROM triggers WHERE enabled = 1"
        rows = await self.pm.fetch_all(sql)
        
        results = []
        for row in rows:
            try:
                # 转换 DB Row -> Pydantic
                data = dict(row)
                data["enabled"] = bool(data["enabled"])
                data["config"] = json.loads(data["config"]) if data["config"] else {}
                data["input_mapping"] = json.loads(data["input_mapping"]) if data["input_mapping"] else {}
                results.append(TriggerDefinition(**data))
            except Exception as e:
                logger.error(f"Failed to load trigger {row['id']}: {e}")
        return results

    async def save(self, trigger: TriggerDefinition):
        """Upsert 触发器"""
        # ... (实现 Insert OR Replace 逻辑，类似 WorkflowRepository) ...
        pass