"""
Goose-System: Python Implementation of AI Agent Framework

A modular, extensible AI Agent framework inspired by Goose-Rs,
supporting skills, tools, providers, extensions, and persistence.
"""

__version__ = "0.1.0"
__author__ = "Goose Team"

from .agent import Agent, AgentConfig
from .skills import (
    Skill,
    SkillLoader,
    SkillRegistry,
    SkillMetadata,
    ProgressiveDisclosureStateMachine,
    SkillState,
    ToolInterceptor,
    ToolPermission,
    ResourceLoader,
    ResourceValidator,
    SandboxIntegrator,
    ExecutionResult,
    StandardPathDiscovery,
    ConfigurablePathDiscovery,
    PathDiscoveryResult,
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
from .tools import (
    Tool,
    ToolRequest,
    ToolResponse,
    ToolExecutor,
    ToolInspector,
    ToolCategory,
    FunctionTool,
    create_builtin_tools,
    register_builtin_tools,
    read_file,
    write_file,
    edit_file,
    glob_files,
    grep_files,
    list_dir,
    run_bash,
)
from .providers import (
    Provider,
    ModelConfig,
    create_provider,
    ProviderFactory,
    OPENAI_AVAILABLE,
    ANTHROPIC_AVAILABLE,
)
from .conversation import Conversation, Message
from .persistence import (
    PersistenceManager,
    BaseRepository,
    with_table,
    TableSpec,
    init_persistence,
    get_persistence,
    shutdown_persistence,
)
from .extension import (
    ExtensionManager,
    Extension,
    ExtensionConfig,
)
from .session import (
    SessionManager,
    SessionType,
    ModelConfig,
    SessionConfig,
    SessionData,
    SessionUpdater,
    InMemorySessionManager,
)
from .mcp import (
    MCPClient,
    MCPClientPool,
    MCPTransport,
    StdioTransport,
    HttpTransport,
    InMemoryTransport,
    ToolDefinition,
    ResourceDefinition,
    InitializeResult,
)
from .managers import (
    RetryManager,
    RetryConfig,
    PermissionManager,
    PermissionLevel,
    SubagentHandler,
    SubagentConfig,
    PromptManager,
    PromptTemplate,
)
from .utils import (
    TokenCounter,
    TokenCountResult,
    TokenBudget,
    create_token_counter,
    count_tokens_for_provider_format,
    estimate_tokens_for_model,
)
from .scheduler import (
    Scheduler,
    SchedulerError,
    ScheduledJob,
    JobStatus,
    JobExecution,
    TaskCallback,
    SimpleAgentTask,
    create_scheduler,
    parse_cron,
)
from .recipe import (
    Recipe,
    RecipeParameter,
    RecipeParameterInputType,
    RecipeParameterRequirement,
    Settings,
    Response,
    Author,
    SubRecipe,
    RenderedRecipe,
    RecipeLoader,
    RecipeExecutor,
    RecipeError,
    create_recipe_loader,
    create_recipe_executor,
)
from .config import (
    Config,
    ConfigError,
    GlobalConfig,
    GooseConfig,
    SecretStorage,
    get_config,
    config_get,
    config_set,
    create_config,
    reset_config,
)
from .chatrecall import (
    ChatRecall,
    ChatRecallConfig,
    ChatRecallResult,
    SessionSummary,
    ChatRecallSearch,
    create_chat_recall,
)
from .todo import (
    TodoItem,
    TodoCreate,
    TodoUpdate,
    TodoFilter,
    TodoStatus,
    TodoPriority,
    TodoListResponse,
    TodoStats,
    TodoManager,
    TodoManagerFactory,
    TodoStorage,
    InMemoryTodoStorage,
    create_todo_manager,
    get_default_todo_manager,
)
from .execution import (
    AgentManager,
    SessionExecutionMode,
    AgentInfo,
    ExecutionContext,
    LRUCache,
    get_agent_manager,
    get_or_create_agent,
    create_execution_context,
)
from .session import (
    SessionManager,
    SessionType,
    ModelConfig,
    SessionConfig,
    SessionData,
    SessionUpdater,
    InMemorySessionManager,
)
from .server import (
    create_app,
    run_server,
    AppState,
)
from .server.state import ServerConfig

__all__ = [
    "Agent",
    "AgentConfig",
    # ... (existing exports)
    # Execution
    "AgentManager",
    "SessionExecutionMode",
    "AgentInfo",
    "ExecutionContext",
    "LRUCache",
    "get_agent_manager",
    "get_or_create_agent",
    "create_execution_context",
    # Session
    "SessionManager",
    "SessionType",
    "ModelConfig",
    "SessionConfig",
    "SessionData",
    "SessionUpdater",
    "InMemorySessionManager",
    # Server
    "create_app",
    "run_server",
    "AppState",
    "ServerConfig",
]
