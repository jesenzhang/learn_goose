import logging
from goose.registry import sys_registry
from goose.workflow.graph import Graph,Node,Edge
from goose.workflow.protocol import WorkflowDefinition
from typing import Dict
from goose.workflow.nodes import ComponentNode


logger = logging.getLogger("goose.workflow.converter")

class WorkflowConverter:
    """
    Compiler: WorkflowDefinition -> Executable Graph
    """
    def __init__(self):
        # [优化] 组件实例缓存池
        # Key: Component Class Name or Type String
        # Value: Component Instance
        self._component_cache: Dict[str, ComponentNode] = {}
        
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
            
            # 2. [优化] 优先从缓存取，没有再实例化
            # 这样无论图里有多少个 LLM 节点，内存里永远只有一个 LLMComponent 实例
            if node_def.type not in self._component_cache:
                self._component_cache[node_def.type] = component_cls()
                logger.debug(f"✨ Instantiated Singleton for {node_def.type}")
            
            component_instance = self._component_cache[node_def.type]
            
            node = Node(
                id=node_def.id,
                component=component_instance, # 逻辑
                config=node_def.config,       # 数据
                inputs=node_def.inputs,       # 数据
                label=getattr(node_def, 'label', None)
            )
            
            graph.add_node(node)
            
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