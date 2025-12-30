from typing import Dict, Any, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field, PrivateAttr, ConfigDict

# 为了避免循环引用，仅在类型检查时导入接口
if TYPE_CHECKING:
    from goose.sandbox import ICodeSandbox
    from goose.resource import ResourceManager
    from goose.workflow.scheduler import WorkflowScheduler # 或者定义一个 Executor Protocol

class WorkflowContext(BaseModel):
    """
    [Core] 工作流执行上下文。
    
    职责：
    1. 状态容器：存储所有节点的输出结果 (node_outputs) 和全局变量 (variables)。
    2. 环境访问：提供对 Sandbox、Resource、Executor 等运行时服务的访问入口。
    3. 序列化：作为 Checkpoint 的一部分被保存到数据库。
    """
    
    # --- 1. 可序列化的状态数据 (State Data) ---
    
    session_id: str = Field(..., description="当前运行的会话 ID")
    
    # 节点输出缓存: {node_id: output_dict}
    # 这是 ValueResolver 解析 {{ node.key }} 的数据源
    node_outputs: Dict[str, Any] = Field(default_factory=dict)
    
    # 全局变量: {key: value}
    # 用于存储 Loop 变量、环境变量或 Start 节点的初始配置
    variables: Dict[str, Any] = Field(default_factory=dict)
    
    # 元数据: 存储如 parent_run_id 等追踪信息
    meta: Dict[str, Any] = Field(default_factory=dict)

    # --- 2. 运行时服务 (Runtime Services) ---
    # 使用 PrivateAttr 防止被 Pydantic 序列化到数据库
    
    _sandbox: Optional['ICodeSandbox'] = PrivateAttr(default=None)
    _resources: Optional['ResourceManager'] = PrivateAttr(default=None)
    _executor: Optional[Any] = PrivateAttr(default=None) # 通常是 Scheduler 实例

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ==========================================
    # Service Injection (依赖注入)
    # ==========================================

    def set_services(
        self, 
        sandbox: Optional['CodeSandbox'] = None,
        resources: Optional['ResourceManager'] = None,
        executor: Optional[Any] = None
    ):
        """
        在 Scheduler 启动或恢复时调用，注入运行时服务。
        """
        if sandbox: self._sandbox = sandbox
        if resources: self._resources = resources
        if executor: self._executor = executor

    @property
    def sandbox(self) -> 'CodeSandbox':
        """
        获取代码沙箱。
        如果未注入，默认返回本地沙箱 (LocalSandbox)。
        """
        if self._sandbox is None:
            from ..core.sandbox import LocalSandbox
            self._sandbox = LocalSandbox()
        return self._sandbox

    @property
    def resources(self) -> 'ResourceManager':
        """
        获取资源管理器 (用于查找 Tool/Plugin 定义)。
        """
        if self._resources is None:
            # 简单的单例回退或报错，取决于架构要求
            # 这里为了方便，我们假设有一个全局注册表的 Wrapper
            from goose.toolkit.protocol import ToolDefinitionRegistry
            
            class SimpleResourceManager:
                async def aget(self, domain, item_id):
                    # 简单桥接到 ToolDefinitionRegistry
                    return ToolDefinitionRegistry.get(item_id)
            
            self._resources = SimpleResourceManager()
            
        return self._resources

    @property
    def executor(self) -> Any:
        """
        获取执行器 (Scheduler)。
        用于 Plugin 组件调用子工作流 (run_sub_workflow)。
        """
        if self._executor is None:
            raise RuntimeError(
                "Executor (Scheduler) not injected into Context. "
                "Cannot run sub-workflows."
            )
        return self._executor

    # ==========================================
    # State Management (状态管理)
    # ==========================================

    def set_node_output(self, node_id: str, output: Any):
        """记录节点输出"""
        self.node_outputs[node_id] = output

    def get_node_output(self, node_id: str) -> Optional[Any]:
        """获取节点输出"""
        return self.node_outputs.get(node_id)

    def update_variables(self, new_vars: Dict[str, Any]):
        """更新全局变量 (通常用于 Loop 变量更新)"""
        self.variables.update(new_vars)

    def clear(self):
        """清空上下文 (慎用)"""
        self.node_outputs.clear()
        self.variables.clear()