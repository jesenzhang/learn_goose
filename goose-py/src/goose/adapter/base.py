from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple,List
from goose.workflow.protocol import WorkflowDefinition
from goose.components.protocol import ComponentMeta

class BaseWorkflowAdapter(ABC):
    """
    工作流适配器基类
    用于将各种异构的前端/导出格式转换为 OpenCoze 标准的 WorkflowDefinition
    """
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """适配器名称，如 'coze_legacy', 'vueflow'"""
        pass

    @abstractmethod
    def transform_workflow(self, data: Dict[str, Any]) -> WorkflowDefinition:
        """
        执行转换逻辑
        :param data: 原始 JSON 数据
        :return: 标准 WorkflowDefinition 对象
        """
        pass
    
    # --- Export: 内部 ComponentMeta -> 外部组件列表格式 ---
    @abstractmethod
    def export_components(self, components: Dict[str, List[ComponentMeta]]) -> Dict[str, Any]:
        """转换：导出组件列表供前端渲染"""
        pass