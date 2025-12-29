import logging
from typing import Dict, Any, List
from pydantic import BaseModel

from ..workflow.graph import Graph
from ..component.registry import ComponentRegistry
from ..workflow.nodes import FunctionNode

logger = logging.getLogger("goose.adapter.vueflow")

# --- VueFlow 数据结构定义 ---
class VueFlowNodeData(BaseModel):
    label: str = "Untitled"
    config: Dict[str, Any] = {} # 静态配置
    inputs: Dict[str, Any] = {} # 输入参数映射 (Template Strings)

class VueFlowNode(BaseModel):
    id: str
    type: str  # Component Name
    data: VueFlowNodeData
    position: Dict[str, float] = {}

class VueFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str = None
    targetHandle: str = None

class VueFlowGraph(BaseModel):
    nodes: List[VueFlowNode]
    edges: List[VueFlowEdge]

# --- 转换器 ---
class VueFlowAdapter:
    """
    将 VueFlow JSON 转换为 Goose Graph
    """
    
    def convert(self, json_data: Dict[str, Any]) -> Graph:
        try:
            # 1. 校验结构
            vf_graph = VueFlowGraph(**json_data)
        except Exception as e:
            raise ValueError(f"Invalid VueFlow JSON format: {e}")

        graph = Graph()
        
        # 2. 转换节点
        for vf_node in vf_graph.nodes:
            # A. 查找组件定义
            component = ComponentRegistry.get(vf_node.type)
            
            if not component:
                logger.warning(f"Unknown component type '{vf_node.type}' for node '{vf_node.id}'. Skipping.")
                continue
                
            # B. 准备数据
            # 确保 config 包含 title/label，方便调试
            config_data = vf_node.data.config.copy()
            config_data["title"] = vf_node.data.label
            
            input_mapping = vf_node.data.inputs

            # C. 调用工厂创建 Node
            try:
                runnable_node = component.create_node(
                    node_id=vf_node.id,
                    config=config_data,
                    inputs=input_mapping
                )
                graph.add_node(vf_node.id, runnable_node)
                
            except Exception as e:
                logger.error(f"Failed to create node {vf_node.id}: {e}")
                raise e

        # 3. 转换连线 (Edges)
        for vf_edge in vf_graph.edges:
            # 简单连线
            # 这里还没处理 If-Else 的 sourceHandle 路由，
            # 如果需要处理条件边，需要类似之前的逻辑：在 Node 工厂里处理，或在这里特殊判断
            
            # 假设 Component 系统里有个特殊组件叫 'router'
            source_comp = ComponentRegistry.get(self._get_node_type(vf_graph, vf_edge.source))
            
            # 如果是条件路由，跳过普通 add_edge (由 Router 组件内部处理条件边)
            # 这里简单处理：直接添加
            graph.add_edge(vf_edge.source, vf_edge.target)

        # 4. 设置入口
        # 寻找 type='start' 的节点
        start_node = next((n for n in vf_graph.nodes if n.type == "start"), None)
        if start_node:
            graph.set_entry_point(start_node.id)
            
        return graph

    def _get_node_type(self, vf_graph: VueFlowGraph, node_id: str) -> str:
        for n in vf_graph.nodes:
            if n.id == node_id:
                return n.type
        return ""