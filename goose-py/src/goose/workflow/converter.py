import logging
from goose.registry import sys_registry
from goose.workflow.graph import Graph
from goose.workflow.protocol import WorkflowDefinition

logger = logging.getLogger("goose.workflow.converter")

class WorkflowConverter:
    """
    Compiler: WorkflowDefinition -> Executable Graph
    """
    def convert(self, definition: WorkflowDefinition) -> Graph:
        graph = Graph()
        
        # 1. 创建节点实例
        for node_def in definition.nodes:
            # 从注册中心获取组件类 (Class)
            entry = sys_registry.components.get_entry(node_def.type)
            component_cls, meta = entry.body,entry.meta
            
            if not component_cls:
                logger.error(f"❌ Component type '{node_def.type}' not found in registry!")
                continue
            
            instance = component_cls()
            instance.raw_config = node_def.config
            # 注入配置 (Runtime State)
            # Scheduler 会读取 instance.config 和 instance.inputs_mapping
            instance.config = node_def.config
            instance.inputs_mapping = node_def.inputs # 之前定义的扁平 Dict
            
            # 元数据注入 (可选，用于调试)
            instance.node_id = node_def.id
            instance.type = node_def.type
            
            graph.add_node(node_def.id, instance)
            logger.info(f"🔨 Built node: {node_def.id} ({node_def.type})")

        # 2. 创建连线
        for edge_def in definition.edges:
            graph.add_edge(
                source=edge_def.source,
                target=edge_def.target,
                source_handle=edge_def.source_handle,
                target_handle=edge_def.target_handle
            )
            
        # 3. 设置入口 (寻找 type=Entry 的节点)
        # 这里的类型字符串必须和注册时的 type 一致
        entry_node = next((n for n in definition.nodes if n.type == "Entry"), None)
        if entry_node:
            graph.set_entry_point(entry_node.id)
        else:
            raise ValueError("Workflow must have an 'Entry' node")
            
        return graph