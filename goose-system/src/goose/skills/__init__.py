"""
Skills Module Init

Skills 模块初始化

提供完整的 Agent Skills 运行时支持:
- 技能加载与解析
- 渐进式披露状态机
- 工具拦截与权限控制
- 资源加载与沙箱执行

Reference:
- Agent Skills 架构设计手册
- Agent Skills 运行时验收测试手册
- goose-rs skills_extension.rs
"""

from .base import (
    Skill,
    SkillMetadata,
    parse_skill_metadata,
    SKILL_NAME_PATTERN,
    MAX_SKILL_NAME_LENGTH,
    MAX_SKILL_DESCRIPTION_LENGTH,
)

from .loader import (
    SkillLoader,
    SkillBackend,
    FilesystemBackend,
    MemoryBackend,
    SKILLS_SYSTEM_PROMPT,
    format_skills_for_prompt,
)

from .registry import (
    SkillRegistry,
    SkillInfo,
)

from .impl_loader import (
    SkillImplLoader,
    load_impl_module,
    get_callable_from_module,
    create_tool_from_impl_function,
    load_skill_with_implementation,
)

# 新增组件
from .state_machine import (
    ProgressiveDisclosureStateMachine,
    SkillState,
    ProgressiveDisclosureState,
)

from .tool_interceptor import (
    ToolInterceptor,
    ToolPermission,
)

from .resource_loader import (
    ResourceLoader,
    ResourceValidator,
)

from .sandbox_integrator import (
    SandboxIntegrator,
    ExecutionResult,
    SandboxConfig,
)

from .path_discovery import (
    StandardPathDiscovery,
    ConfigurablePathDiscovery,
    PathDiscoveryResult,
    validate_skill_path,
    normalize_skill_path,
)

from .security import (
    SecurityLevel,
    SecurityViolation,
    ThreatType,
    SecurityCheckResult,
    SecurityReport,
    EnhancedStaticScanner,
    ArtifactSanitizer,
    SecurityManager,
    PromptInjectionDefense,
)

__all__ = [
    # 基础组件
    "Skill",
    "SkillMetadata",
    "parse_skill_metadata",
    "SKILL_NAME_PATTERN",
    "MAX_SKILL_NAME_LENGTH",
    "MAX_SKILL_DESCRIPTION_LENGTH",
    
    # 加载器
    "SkillLoader",
    "SkillBackend",
    "FilesystemBackend",
    "MemoryBackend",
    "SKILLS_SYSTEM_PROMPT",
    "format_skills_for_prompt",
    
    # 注册表
    "SkillRegistry",
    "SkillInfo",
    
    # 实现加载器
    "SkillImplLoader",
    "load_impl_module",
    "get_callable_from_module",
    "create_tool_from_impl_function",
    "load_skill_with_implementation",
    
    # 渐进式披露
    "ProgressiveDisclosureStateMachine",
    "SkillState",
    "ProgressiveDisclosureState",
    
    # 工具拦截
    "ToolInterceptor",
    "ToolPermission",
    
    # 资源加载
    "ResourceLoader",
    "ResourceValidator",
    
    # 沙箱集成
    "SandboxIntegrator",
    "ExecutionResult",
    "SandboxConfig",
    
    # 路径发现
    "StandardPathDiscovery",
    "ConfigurablePathDiscovery",
    "PathDiscoveryResult",
    "validate_skill_path",
    "normalize_skill_path",
    
    # 安全模块 (v2.0)
    "SecurityLevel",
    "SecurityViolation",
    "ThreatType",
    "SecurityCheckResult",
    "SecurityReport",
    "EnhancedStaticScanner",
    "ArtifactSanitizer",
    "SecurityManager",
    "PromptInjectionDefense",
]

__version__ = "1.0.0"
