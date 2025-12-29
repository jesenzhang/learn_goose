import logging
import json
from typing import Dict, Any, List, Optional, Callable, Union

from simpleeval import SimpleEval

# Core Graph Elements
from .graph import Graph
from .runnable import Runnable
from .protocol import WorkflowDefinition, NodeConfig, EdgeConfig

# Nodes
from .nodes import FunctionNode, AgentNode, ToolNode, MapNode
from .subgraph import SubgraphNode

# Logic Helper
from ..agent import Agent
from ..tools.base import Tool

logger = logging.getLogger("goose.workflow.converter")

class ResourceLoader:
    """
    资源加载接口。
    负责根据 JSON 配置中的 ID 加载实际的 Python 对象 (Agent/Tool)。
    在实际应用中，这应该连接到您的 ComponentRegistry 或数据库。
    """
    def load_agent(self, config: Dict[str, Any]) -> Agent:
        # TODO: Implement actual loading logic
        agent_id = config.get("agent_id") or config.get("model", {}).get("name", "MockAgent")
        return Agent(name=agent_id, provider=None) # Placeholder

    def load_tool(self, config: Dict[str, Any]) -> Tool:
        # TODO: Implement actual loading logic
        tool_name = config.get("tool_name", "MockTool")
        return Tool(name=tool_name, func=lambda: "Tool Result", description="Mock")

class WorkflowConverter:
    """
    将前端 JSON (WorkflowDefinition) 编译为可执行的 Graph 对象。
    """
    def __init__(self, resource_loader: ResourceLoader = None):
        self.loader = resource_loader or ResourceLoader()

    def convert(self, definition: WorkflowDefinition) -> Graph:
        """主入口：编译 JSON 为 Graph"""
        graph = Graph()
        
        # 1. 转换所有节点
        # 我们使用两遍扫描：第一遍创建节点，第二遍处理特殊的控制流连接
        for node_def in definition.nodes:
            try:
                if node_def.type == "if-else":
                    # If-Else 需要特殊处理：它由一个计算节点 + 条件边组成
                    self._handle_selector_node(graph, node_def, definition.edges)
                else:
                    # 普通节点
                    runnable = self._create_node_instance(node_def)
                    if runnable:
                        graph.add_node(node_def.id, runnable)
            except Exception as e:
                logger.error(f"Failed to convert node {node_def.id} ({node_def.type}): {e}")
                raise e

        # 2. 转换普通连线 (Edges)
        # 排除那些源头是 If-Else 的边 (它们已经在 _handle_selector_node 中处理了)
        for edge in definition.edges:
            if not self._is_conditional_source(definition, edge.source):
                # 普通数据流连线
                graph.add_edge(edge.source, edge.target)

        # 3. 设置入口点
        # 寻找 type='start' 的节点
        start_nodes = [n for n in definition.nodes if n.type == "start"]
        if start_nodes:
            graph.set_entry_point(start_nodes[0].id)
        else:
            # 如果没有显式 start，尝试找没有入边的节点 (简单的 DAG 逻辑)
            # 或者抛出异常
            pass

        return graph

    # ==========================================
    # 节点工厂
    # ==========================================

    def _create_node_instance(self, node_def: NodeConfig) -> Optional[Runnable]:
        """根据类型分发创建逻辑"""
        
        # 转换输入映射: InputSource -> "{{ ref }}"
        inputs_mapping = self._convert_inputs(node_def.inputs.parameters)

        if node_def.type == "start":
            # Start 节点：透传输入，也可以做 Schema 校验
            return FunctionNode(lambda **kwargs: kwargs, inputs=inputs_mapping, name="Start")

        elif node_def.type == "end":
            # End 节点：透传输出
            return FunctionNode(lambda **kwargs: kwargs, inputs=inputs_mapping, name="End")

        elif node_def.type == "llm" or node_def.type == "agent":
            # Agent 节点
            agent = self.loader.load_agent(node_def.config)
            return AgentNode(agent, inputs=inputs_mapping, name=node_def.title)

        elif node_def.type == "tool":
            # Tool 节点
            tool = self.loader.load_tool(node_def.config)
            return ToolNode(tool, inputs=inputs_mapping)

        elif node_def.type == "code":
            # Code 节点：动态编译 Python 代码
            code_str = node_def.config.get("code", "")
            func = self._compile_code(code_str)
            return FunctionNode(func, inputs=inputs_mapping, name=node_def.title)

        elif node_def.type == "loop":
            # Loop 节点：递归处理
            return self._create_loop_node(node_def, inputs_mapping)
        
        elif node_def.type == "sub-workflow":
             # 引用其他工作流 ID
             # 这里需要根据 ID 加载另一个 JSON 定义并递归 convert
             # 暂未实现加载逻辑
             pass

        logger.warning(f"Unknown node type: {node_def.type}, skipping.")
        return None

    # ==========================================
    # 核心逻辑：控制流适配
    # ==========================================

    def _handle_selector_node(self, graph: Graph, node_def: NodeConfig, all_edges: List[EdgeConfig]):
        """
        将前端的 If-Else 节点转换为 Graph 的 Node + Conditional Edge
        """
        # 1. 创建计算节点 (FunctionNode)
        # 它负责评估条件，并返回 active_handle (例如 "true", "case_1")
        conditions = node_def.config.get("conditions", [])
        default_handle = node_def.config.get("default_handle", "else")
        inputs_mapping = self._convert_inputs(node_def.inputs.parameters)

        def selector_logic(**kwargs):
            # 使用 simpleeval 安全评估表达式
            # kwargs 包含了所有 resolve 后的输入变量
            evaluator = SimpleEval(names=kwargs)
            
            for cond in conditions:
                expr = cond.get("expression")
                target_handle = cond.get("target_handle")
                try:
                    # 替换表达式中的变量引用 (如果有必要，通常 simpleeval 可以直接处理 names)
                    if evaluator.eval(expr):
                        logger.info(f"⚖️ If-Else '{node_def.title}': '{expr}' is True -> {target_handle}")
                        return target_handle
                except Exception as e:
                    logger.warning(f"If-Else eval error '{expr}': {e}")
            
            logger.info(f"⚖️ If-Else '{node_def.title}': Default -> {default_handle}")
            return default_handle

        selector_node = FunctionNode(selector_logic, inputs=inputs_mapping, name=f"Selector_{node_def.id}")
        graph.add_node(node_def.id, selector_node)

        # 2. 构建条件路由表 (Handle -> TargetNodeID)
        # 查找所有源头是这个节点的边
        out_edges = [e for e in all_edges if e.source == node_def.id]
        
        path_map = {} # { "true": "node_b", "false": "node_c" }
        for edge in out_edges:
            # 前端 JSON 的 Edge 上必须有 source_handle 来标识这是哪条分支
            if edge.source_handle:
                path_map[edge.source_handle] = edge.target
            else:
                # 容错：如果没有 handle，假设它是 default
                path_map[default_handle] = edge.target

        # 3. 定义 Router 函数
        def router(context):
            # 获取 Selector 节点的输出
            # FunctionNode 默认返回 {"output": result}
            node_out = context.get_node_output(node_def.id)
            if not node_out:
                return None
            
            handle = node_out.get("output")
            target_node = path_map.get(handle)
            
            if not target_node:
                logger.warning(f"❌ If-Else '{node_def.id}' returned handle '{handle}', but no edge connected.")
                # 可以选择返回 "__END__" 或者抛错
                
            return target_node

        # 4. 添加条件边
        graph.add_conditional_edge(node_def.id, router)

    # ==========================================
    # 核心逻辑：递归子图/循环
    # ==========================================

    def _create_loop_node(self, node_def: NodeConfig, inputs_mapping: Dict[str, Any]):
        """
        创建循环节点。目前主要支持 Array 模式 (对应 MapNode)。
        """
        loop_type = node_def.config.get("loopType", "array")
        sub_wf_json = node_def.config.get("sub_workflow")
        
        if not sub_wf_json:
            raise ValueError(f"Loop node {node_def.id} missing sub_workflow")

        # 1. 递归转换子工作流
        # 注意：这里假设 sub_wf_json 也是符合 WorkflowDefinition 结构的字典
        # 实际情况中，前端传来的可能是简化版，需要适配
        # 这里做个简单的适配层
        if "nodes" not in sub_wf_json:
             # 有时候前端只传了 nodes/edges 列表，没传 id/name
             sub_wf_def = WorkflowDefinition(
                 id=f"{node_def.id}_sub", 
                 nodes=sub_wf_json.get("nodes", []),
                 edges=sub_wf_json.get("edges", [])
             )
        else:
            sub_wf_def = WorkflowDefinition(**sub_wf_json)
            
        sub_graph = self.convert(sub_wf_def)

        # 2. 包装为 SubgraphNode
        # 这里的 inputs={} 是空的，因为 Loop 内部的数据流转是特殊的
        # 数据流转由 MapNode 或 Loop 逻辑控制
        inner_subgraph_node = SubgraphNode(
            sub_graph, 
            inputs={}, # 这里的 inputs 映射是在运行时由 MapNode 动态注入的
            name=f"LoopBody_{node_def.id}"
        )

        # 3. 根据类型包装
        if loop_type == "array":
            # MapNode: 并发执行
            # inputs_mapping 中必须包含指向列表的引用，例如 {"list": "{{ node.list_data }}"}
            # 我们需要确保 JSON 中的配置正确映射到了 'list' 这个 key
            return MapNode(inner_subgraph_node, inputs=inputs_mapping)
        
        else:
            # Count 模式或其他模式，暂未实现专门的 Node，可以用 SubgraphNode 配合内部逻辑
            logger.warning("Count loop not fully implemented, creating single run subgraph.")
            return inner_subgraph_node

    # ==========================================
    # 辅助工具
    # ==========================================

    def _convert_inputs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        将前端 InputSource (Ref/Value) 转换为 CozeNodeMixin 支持的格式
        Ref -> "{{ node.key }}"
        Value -> raw value
        """
        return params

    def _is_conditional_source(self, definition: WorkflowDefinition, node_id: str) -> bool:
        """检查节点是否是控制流节点"""
        for n in definition.nodes:
            if n.id == node_id and n.type == "if-else":
                return True
        return False

    def _compile_code(self, code_str: str) -> Callable:
        """
        编译动态代码。
        ⚠️ 警告：这有安全风险，生产环境应使用沙箱 (如 gVisor / Firecracker)。
        """
        if not code_str:
            return lambda **k: None
            
        def generated_func(**kwargs):
            local_scope = kwargs.copy() # 将输入变量注入局部作用域
            try:
                exec(code_str, {}, local_scope)
                # 约定：代码中必须定义 main 函数，或者直接修改 inputs
                if "main" in local_scope and callable(local_scope["main"]):
                    return local_scope["main"](**kwargs)
                else:
                    return local_scope.get("output", "No output or main() found")
            except Exception as e:
                raise RuntimeError(f"Code execution failed: {e}")
                
        return generated_func