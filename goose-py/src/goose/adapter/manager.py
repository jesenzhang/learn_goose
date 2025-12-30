from typing import Dict, Any, List, Optional
from goose.workflow.protocol import WorkflowDefinition
from goose.components.protocol import ComponentMeta
from .base import BaseWorkflowAdapter

class AdapterManager:
    _adapters: Dict[str, BaseWorkflowAdapter] = {}

    @classmethod
    def register(cls, adapter: BaseWorkflowAdapter):
        cls._adapters[adapter.format_name] = adapter

    @classmethod
    def get_adapter(cls, name: str) -> Optional[BaseWorkflowAdapter]:
        return cls._adapters.get(name)

    @classmethod
    def import_workflow(cls, data: Dict[str, Any], format_type: str = None) -> WorkflowDefinition:
        """
        导入工作流
        :param format_type: 指定格式，如果为空则自动嗅探
        """
        if format_type and format_type in cls._adapters:
            adapter = cls._adapters.get(format_type)
            if not adapter:
                raise ValueError(f"Unknown format: {format_type}")
            return adapter.transform_workflow(data)
        
        # 自动嗅探
        for adapter in cls._adapters.values():
            if adapter.match(data):
                return adapter.transform_workflow(data)
        
        raise ValueError("Unknown workflow format")

    @classmethod
    def export_components(cls, components: Dict[str, List[ComponentMeta]], format_type: str) -> Dict[str, Any]:
        """导出组件列表"""
        adapter = cls._adapters.get(format_type)
        if not adapter:
            raise ValueError(f"Unknown format: {format_type}")
        return adapter.export_components(components)
