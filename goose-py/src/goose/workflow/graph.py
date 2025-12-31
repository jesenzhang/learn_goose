from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union,Callable

# 为了避免运行时循环引用，我们在类型检查阶段引入 Runnable
# 在运行时，nodes 只是 Dict[str, Any]
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .runnable import Runnable
    from .nodes import ComponentNode

# 路由函数：接收上下文，返回下一个节点 ID
Router = Callable[["WorkflowContext"], str]
@dataclass
class Node:
    """
    [Graph Node] 图节点
    它是静态配置和动态逻辑的结合点。
    """
    id: str
    component: ComponentNode  # 无状态组件实例 (单例)
    
    # [核心] 配置数据存储在这里，而不是 component 内部
    config: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict) # 输入映射 ({{ ref }})
    
    label: Optional[str] = None
    
@dataclass
class Edge:
    """
    有向图容器 (Directed Graph Container)。
    采用邻接表 (Adjacency List) 存储结构。
    
    职责：
    1. 存储节点 (Nodes) 和 边 (Edges)。
    2. 提供拓扑查询接口 (get_outgoing_edges)。
    3. 不包含任何执行逻辑。
    """
    source: str
    target: str
    
    # [Protocol] 出发端口 ID
    # 如果是 If-Else 节点，这里会存储 "true", "false", "case_1" 等
    # 如果是普通节点，这里通常为 None
    source_handle: Optional[str] = None 
    
    # [Protocol] 目标端口 ID (可选，用于数据映射)
    target_handle: Optional[str] = None
    
class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        # 边可以是静态 ID，也可以是动态 Router 函数
        self.edges: Dict[str, List[Edge]] = {}
        self.entry_point: Optional[str] = None

    def add_node(self,node: Node):
        """
        添加节点。
        :param node_id: 唯一标识
        :param runnable: 可执行对象 (通常是 Runnable 子类)
        """
        node_id = node.id
        if node_id in self.nodes:
            raise ValueError(f"Node {node_id} already exists.")
            
        self.nodes[node_id] = node
        # 初始化该节点的出边列表
        if node_id not in self.edges:
            self.edges[node_id] = []
            
    def add_node_from(self, node_id: str, component: ComponentNode, config: Dict = None, inputs: Dict = None, label: str = None):
        """辅助方法：语法糖，内部委托给 add_node"""
        # 仅仅负责构造，逻辑委托给核心方法
        node = Node(
            id=node_id, 
            component=component, 
            config=config or {}, 
            inputs=inputs or {}, 
            label=label
        )
        self.add_node(node)
        
        
    def add_edge(self, source: str, target: str, source_handle: str = None, target_handle: str = None):
        """
        [核心] 添加边。
        
        :param source: 源节点 ID
        :param target: 目标节点 ID
        :param source_handle: (控制流关键) 指定从哪个端口流出。
                              如果不传，表示该边总是激活。
                              如果传了 (e.g. "true")，Scheduler 只有在源节点返回 _active_handle="true" 时才走这条边。
        """
        if source not in self.nodes:
            raise ValueError(f"Source node '{source}' not found. Add node first.")
        if target not in self.nodes:
            raise ValueError(f"Target node '{target}' not found. Add node first.")
        
        edge = Edge(
            source=source, 
            target=target, 
            source_handle=source_handle, 
            target_handle=target_handle
        )
        
        self.edges[source].append(edge)
        
    def add_conditional_edge(self, source: str, *args, **kwargs):
        """
        [兼容性接口] 
        旧版 Graph 可能使用此方法添加动态路由。
        在新的数据驱动协议下，条件边本质上就是带有 source_handle 的普通边。
        建议抛出弃用警告或直接映射逻辑。
        """
        import warnings
        warnings.warn(
            "add_conditional_edge is deprecated. Use add_edge(source, target, source_handle=...) instead.",
            DeprecationWarning
        )
        # 这里无法直接映射，因为旧版参数通常是 Router 函数，而新版是静态数据。
        # 建议在 Adapter 层处理转换逻辑。
        pass
    
    
    def set_entry_point(self, node_id: str):
        """设置图的起始节点"""
        if node_id not in self.nodes:
            raise ValueError(f"Entry point '{node_id}' not found in graph.")
        self.entry_point = node_id

    # ==========================================
    # 查询接口 (供 Scheduler 使用)
    # ==========================================

    def get_node(self, node_id: str) -> Optional[Node]:
        """获取节点实例"""
        return self.nodes.get(node_id)

    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """
        获取某节点的所有出边。
        Scheduler 将根据这些边的 source_handle 属性和节点的输出结果来决定下一跳。
        """
        return self.edges.get(node_id, [])

    def validate(self):
        """
        (可选) 校验图的完整性
        1. Entry point 是否存在
        2. 是否有悬空边 (Target 不存在)
        """
        if not self.entry_point:
            raise ValueError("Graph must have an entry point defined.")
        
        for source_id, edges in self.edges.items():
            for edge in edges:
                if edge.target not in self.nodes:
                    raise ValueError(f"Edge from {source_id} points to missing node {edge.target}")