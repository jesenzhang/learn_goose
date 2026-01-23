"""
Agent Base

Agent 基类，参考 Goose-Rs 的 Agent 结构设计。
集成六个管理器：
- Extension Manager: 插件生命周期管理
- Retry Manager: 自动重试
- Tool Inspection Manager: 工具检查链 (Security → Permission → Repetition)
- Prompt Manager: 提示模板管理
- Subagent Handler: 子代理执行
- Permission Manager: 权限确认
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass, field
import asyncio
import uuid

from .state import AgentState, SkillsState, SessionState
from .reply import AgentReply, ReplyContext, ReplyConfig
from .event import AgentEvent, EventStream
from ..conversation import Conversation, Message
from ..skills import Skill, SkillRegistry
from ..skills.loader import SkillLoader
from ..providers import Provider, ProviderWrapper
from ..managers import (
    RetryManager,
    ToolInspectionManager,
    PromptManager,
    SubagentHandler,
    PermissionManager,
    PromptCategory,
    PromptTemplate,
)
from ..extension import ExtensionManager, ExtensionConfig
from ..truncation import TruncationManager, TruncationConfig, create_truncation_manager


@dataclass
class AgentConfig:
    """Agent 配置"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    max_turns: int = 100
    max_iterations: int = 1000
    compact_threshold: float = 0.8
    compact_ratio: float = 0.5
    chat_mode: bool = False
    system_prompt: str = ""

    @classmethod
    def default(cls) -> "AgentConfig":
        """创建默认配置"""
        return cls()


class Agent:
    """
    Goose-System Agent

    核心 Agent 类，协调所有组件完成对话任务。

    六个管理器集成：
    1. Extension Manager - 插件生命周期管理
    2. Retry Manager - 自动重试
    3. Tool Inspection Manager - 工具检查链
    4. Prompt Manager - 提示模板管理
    5. Subagent Handler - 子代理执行
    6. Permission Manager - 权限确认
    """

    def __init__(
        self,
        provider: Provider,
        config: Optional[AgentConfig] = None
    ):
        self.config = config or AgentConfig.default()
        self.provider = provider

        self.session_state = SessionState(
            session_id=self.config.session_id,
            max_turns=self.config.max_turns
        )

        self.conversation = Conversation()

        self._tools: Dict[str, Any] = {}

        self.skill_registry = SkillRegistry()
        self.skill_loader = SkillLoader()

        self.extension_manager = ExtensionManager()

        self.retry_manager = RetryManager()

        self.inspection_manager = ToolInspectionManager().create_default_chain()

        self.prompt_manager = PromptManager()

        self.subagent_handler = SubagentHandler(self)

        self.permission_manager = PermissionManager()

        self.truncation_manager: Optional[TruncationManager] = None

        self.event_stream = EventStream()

        self._subagents: Dict[str, "Agent"] = {}

        if self.config.system_prompt:
            self.conversation.set_system_prompt(self.config.system_prompt)

    async def init_truncation_manager(
        self,
        enabled: bool = True,
        threshold: Optional[float] = None,
        auto_compact: Optional[bool] = None,
        max_messages_before_compact: Optional[int] = None,
        keep_recent_messages: Optional[int] = None
    ) -> None:
        """Initialize the truncation manager with optional configuration"""
        if self.truncation_manager is not None:
            return

        config = TruncationConfig(
            enabled=enabled,
            threshold=threshold if threshold is not None else self.config.compact_threshold,
            auto_compact=auto_compact if auto_compact is not None else True,
            max_messages_before_compact=max_messages_before_compact or 50,
            keep_recent_messages=keep_recent_messages or 5
        )
        self.truncation_manager = await create_truncation_manager(
            self.provider,
            config
        )

    async def update_provider(self, provider: Provider) -> None:
        """Update the provider (useful for switching models mid-session)"""
        self.provider = provider
        if self.truncation_manager is not None:
            self.truncation_manager.provider = provider

    async def persist_session(self) -> Dict[str, Any]:
        """Persist session state to a serializable dictionary"""
        return {
            "session_id": self.config.session_id,
            "turn_count": self.session_state.turn_count,
            "messages": [
                {
                    "role": msg.role.value,
                    "content": msg.content,
                    "timestamp": getattr(msg, "timestamp", None)
                }
                for msg in self.conversation.messages
            ],
            "system_prompt": self.conversation.system_prompt
        }

    async def restore_session(self, data: Dict[str, Any]) -> None:
        """Restore session from a serialized dictionary"""
        self.config.session_id = data.get("session_id", self.config.session_id)
        self.session_state.turn_count = data.get("turn_count", 0)

        for msg_data in data.get("messages", []):
            role = msg_data.get("role", "user")
            content = msg_data.get("content", "")
            if role == "user":
                self.conversation.add_user_message(content)
            elif role == "assistant":
                self.conversation.add_assistant_message(content)

        if data.get("system_prompt"):
            self.conversation.set_system_prompt(data["system_prompt"])

    @property
    def tools(self) -> List[Any]:
        """获取所有工具"""
        return list(self._tools.values())

    def register_tool(self, tool: Any) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> Optional[Any]:
        """注销工具"""
        return self._tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[Any]:
        """获取工具"""
        return self._tools.get(name)

    def register_extension(self, config: ExtensionConfig) -> None:
        """注册扩展"""
        self.extension_manager.register_extension(config)

    async def load_extension(self, name: str) -> None:
        """加载扩展"""
        extension = await self.extension_manager.load_extension(name)
        for tool in extension.tools:
            self.register_tool(tool)

    async def load_all_extensions(self) -> None:
        """加载所有扩展"""
        await self.extension_manager.load_all()
        for extension in self.extension_manager.extensions.values():
            if extension.is_connected:
                for tool in extension.tools:
                    self.register_tool(tool)

    def load_skill(self, skill_path: str) -> Skill:
        """加载 Skill"""
        skill = self.skill_loader.load_skill(skill_path)
        self.skill_registry.register(skill)

        for tool_dict in skill.get_tools():
            tool = self._create_tool_from_dict(tool_dict)
            if tool:
                self.register_tool(tool)

        return skill

    def _create_tool_from_dict(self, tool_dict: Dict[str, Any]) -> Optional[Any]:
        """从字典创建工具"""
        from ..tools import FunctionTool
        name = tool_dict.get("name", "")
        description = tool_dict.get("description", "")

        if not name:
            return None

        def dummy_function(**kwargs):
            return {"result": "Tool not fully implemented"}

        return FunctionTool(
            name=name,
            description=description,
            parameters=tool_dict.get("parameters", {}),
            function=dummy_function
        )

    def load_skills_from_dir(self, directory: str) -> List[Skill]:
        """从目录加载所有 Skills"""
        skills = self.skill_loader.load_skills_from_directory(directory)
        for skill in skills:
            self.skill_registry.register(skill)
            for tool_dict in skill.get_tools():
                tool = self._create_tool_from_dict(tool_dict)
                if tool:
                    self.register_tool(tool)
        return skills

    def add_system_prompt(self, prompt: str) -> None:
        """添加系统提示"""
        self.conversation.set_system_prompt(prompt)

    def add_prompt_template(
        self,
        name: str,
        template: str,
        category: str = "default"
    ) -> None:
        """添加提示模板"""
        cat = PromptCategory.CUSTOM
        if category == "system":
            cat = PromptCategory.SYSTEM
        elif category == "task":
            cat = PromptCategory.TASK
        elif category == "context":
            cat = PromptCategory.CONTEXT
        elif category == "tool":
            cat = PromptCategory.TOOL

        prompt_template = PromptTemplate(
            name=name,
            content=template,
            category=cat
        )
        self.prompt_manager.add_template(prompt_template)

    def get_prompt(self, name: str, **kwargs) -> str:
        """获取提示模板"""
        template = self.prompt_manager.get_template(name)
        if template:
            return template.render(kwargs)
        return ""

    async def run_subagent(
        self,
        task_prompt: str,
        system_prompt: str,
        max_turns: int = 50
    ) -> Conversation:
        """运行子 Agent 任务"""
        from ..managers import SubagentConfig
        config = SubagentConfig(
            name=f"subagent_{uuid.uuid4().hex[:8]}",
            instructions=system_prompt,
            max_turns=max_turns
        )

        result = await self.subagent_handler.execute_subagent(config)

        conversation = Conversation()
        conversation.set_system_prompt(system_prompt)
        conversation.add_user_message(task_prompt)

        for msg_data in result.messages:
            conversation.add_assistant_message(msg_data.get("content", ""))

        return conversation

    async def with_retry(self, func, *args, **kwargs):
        """带重试的函数执行"""
        return await self.retry_manager.execute_with_retry(func, *args, **kwargs)

    async def check_tool_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """检查工具权限"""
        return await self.permission_manager.check_permission(
            tool_name, arguments
        )

    async def inspect_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """检查工具"""
        from ..managers import ToolRequest
        request = ToolRequest(
            id=str(uuid.uuid4()),
            name=tool_name,
            arguments=arguments
        )
        return await self.inspection_manager.inspect(request)

    async def reply(
        self,
        user_message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> AgentState:
        """处理用户消息并生成回复"""
        try:
            self.conversation.add_user_message(user_message, attachments or [])

            reply_config = ReplyConfig(
                max_turns=self.config.max_turns,
                max_iterations=self.config.max_iterations,
                compact_threshold=self.config.compact_threshold,
                compact_ratio=self.config.compact_ratio,
                chat_mode=self.config.chat_mode
            )

            context = ReplyContext(
                conversation=self.conversation,
                tools=self.tools,
                system_prompt=self.conversation.system_prompt or "",
                config=reply_config
            )

            reply_handler = AgentReply(
                provider=self.provider,
                context=context,
                event_stream=self.event_stream,
                truncation_manager=self.truncation_manager
            )

            state = await reply_handler.run()

            if not isinstance(state, SkillsState):
                skills_state = SkillsState(
                    messages=state.messages,
                    jump_to=state.jump_to,
                    structured_response=state.structured_response
                )
                state = skills_state

            self.session_state.conversation_state = state

            return state
        except Exception as e:
            await self.event_stream.push(AgentEvent.error(e))
            raise

    async def reply_stream(
        self,
        user_message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式处理用户消息"""
        try:
            self.conversation.add_user_message(user_message, attachments or [])

            reply_config = ReplyConfig(
                max_turns=self.config.max_turns,
                max_iterations=self.config.max_iterations,
                compact_threshold=self.config.compact_threshold,
                compact_ratio=self.config.compact_ratio,
                chat_mode=self.config.chat_mode
            )

            context = ReplyContext(
                conversation=self.conversation,
                tools=self.tools,
                system_prompt=self.conversation.system_prompt or "",
                config=reply_config
            )

            reply_handler = AgentReply(
                provider=self.provider,
                context=context,
                event_stream=self.event_stream,
                truncation_manager=self.truncation_manager
            )

            async for event in reply_handler.run_stream():
                yield event
        except Exception as e:
            await self.event_stream.push(AgentEvent.error(e))
            yield AgentEvent.error(e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的模式定义（用于 Provider）"""
        return [tool.to_dict() for tool in self.tools]

    def get_skill_descriptions(self) -> List[Dict[str, str]]:
        """获取所有 Skill 的描述（用于提示）"""
        descriptions = []
        for skill in self.skill_registry.list_skills():
            descriptions.append({
                "name": skill.name,
                "description": skill.description,
                "path": skill.path
            })
        return descriptions

    def get_session_info(self) -> Dict[str, Any]:
        """获取会话信息"""
        return {
            "session_id": self.config.session_id,
            "turn_count": self.session_state.turn_count,
            "max_turns": self.config.max_turns,
            "tool_count": len(self._tools),
            "skill_count": self.skill_registry.count,
            "message_count": len(self.conversation.messages),
            "model": self.provider.get_model_config().model_name
        }

    def get_manager_status(self) -> Dict[str, Any]:
        """获取所有管理器状态"""
        return {
            "extension_manager": {
                "extensions": len(self.extension_manager.extensions),
                "tools": len(self.extension_manager.all_tools)
            },
            "retry_manager": {},
            "inspection_manager": {
                "enabled": self.inspection_manager._enabled,
                "inspectors": [i.name for i in self.inspection_manager.inspectors]
            },
            "prompt_manager": {
                "templates": len(self.prompt_manager.templates)
            },
            "permission_manager": self.permission_manager.get_permission_summary()
        }

    def clear_history(self) -> None:
        """清空对话历史（保留系统提示）"""
        system_prompt = self.conversation.system_prompt
        self.conversation = Conversation()
        if system_prompt:
            self.conversation.set_system_prompt(system_prompt)
