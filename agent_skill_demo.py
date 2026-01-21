"""
Minimal AgentMiddleware and Skills Framework Implementation

This module provides a complete, standalone implementation of:
- AgentMiddleware: Base middleware class with lifecycle hooks
- SkillsMiddleware: Agent Skills specification implementation
- Backend Protocol: Pluggable storage abstraction
- SimpleAgent: Agent with middleware support and Provider integration

No LangChain dependencies required.

Usage:
    python agent_skill_demo.py

References:
- Agent Skills Specification: https://agentskills.io/specification
- LangChain AgentMiddleware: langchain.agents.middleware.types
- deepagents: F:\\Workspace\\learn_goose\\deepagents
"""

import sys
import os
from pathlib import Path

assistant_path = Path(__file__).parent / "assistant" / "src"
if assistant_path.exists() and str(assistant_path) not in sys.path:
    sys.path.insert(0, str(assistant_path))
    print(f"  [Info] Added assistant path to sys.path: {assistant_path}")

from abc import ABC, abstractmethod
from typing import (
    TypeVar, Generic, Type, Callable, Dict, List, Optional, 
    Any, Tuple, Union
)
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import asyncio
import re
import yaml


# =============================================================================
# Type Variables
# =============================================================================
StateT = TypeVar('StateT')
ContextT = TypeVar('ContextT')


# =============================================================================
# Provider Integration (from assistant)
# =============================================================================
try:
    import assistant.providers  # Ensure providers package is accessible
    from assistant.providers.base import BaseLLM, Usage
    from assistant.providers.factory import ProviderFactory
    from assistant.providers.model_config import ModelConfig
    from assistant.conversation import Message as AssistantMessage, Role, TextContent, ToolRequest, ToolResponse, ToolCall
    PROVIDER_AVAILABLE = True
except ImportError as e:
    print(f"[Warning] Provider modules not available: {e}")
    PROVIDER_AVAILABLE = False
    BaseLLM = None
    Usage = None
    ProviderFactory = None
    ModelConfig = None
    AssistantMessage = None


# =============================================================================
# Core Enums and Data Classes
# =============================================================================
class JumpTo(str, Enum):
    """Control flow destinations for agent execution."""
    TOOLS = "tools"
    MODEL = "model"
    END = "end"


@dataclass
class AgentState:
    """Core state schema for agents."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    jump_to: Optional[str] = None
    structured_response: Optional[Any] = None
    
    def model_copy(self) -> 'AgentState':
        """Create a copy of the state."""
        return AgentState(
            messages=self.messages.copy(),
            jump_to=self.jump_to,
            structured_response=self.structured_response
        )


@dataclass 
class SkillsState(AgentState):
    """State with skills support."""
    skills_metadata: Optional[List[Dict]] = None


@dataclass
class ModelRequest:
    """Model request information."""
    model_name: str
    messages: List[Dict[str, Any]]
    tools: List[Dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    
    def override(self, **kwargs) -> 'ModelRequest':
        """Create a new request with overrides."""
        data = self.__dict__.copy()
        data.update(kwargs)
        return ModelRequest(**data)


@dataclass
class ModelResponse:
    """Model response information."""
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolCallRequest:
    """Tool call request information."""
    tool_name: str
    args: Dict[str, Any]
    tool_call_id: str


@dataclass
class ToolResponse:
    """Tool execution response."""
    content: Any
    tool_call_id: str
    success: bool = True


class Runtime:
    """Runtime context for agent execution."""
    
    def __init__(self, context: Dict[str, Any] = None):
        self.context = context or {}
    
    def stream_write(self, event: Dict[str, Any]) -> None:
        """Write streaming event."""
        print(f"  [Stream] {event}")


# =============================================================================
# Backend Protocol - Pluggable Storage
# =============================================================================
@dataclass
class FileInfo:
    """File listing information."""
    path: str
    is_dir: Optional[bool] = None
    size: Optional[int] = None


@dataclass
class FileDownloadResponse:
    """File download result."""
    path: str
    content: Optional[bytes] = None
    error: Optional[str] = None


@dataclass
class FileUploadResponse:
    """File upload result."""
    path: str
    error: Optional[str] = None


class BackendProtocol(ABC):
    """Protocol for pluggable storage backends."""
    
    def ls_info(self, path: str) -> List[FileInfo]:
        """List directory contents."""
        return []
    
    def download_files(self, paths: List[str]) -> List[FileDownloadResponse]:
        """Download multiple files."""
        return []
    
    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[FileUploadResponse]:
        """Upload multiple files."""
        return []


class MemoryBackend(BackendProtocol):
    """In-memory backend for testing and development."""
    
    def __init__(self):
        self.files: Dict[str, bytes] = {}
    
    def ls_info(self, path: str) -> List[FileInfo]:
        """List directory contents from memory."""
        items = []
        prefix = path.rstrip('/') + '/'
        
        for file_path in self.files.keys():
            if file_path.startswith(prefix) and len(file_path) > len(prefix):
                relative = file_path[len(prefix):]
                if '/' not in relative:
                    is_dir = any(
                        file_path.startswith(prefix + relative + '/')
                        for file_path in self.files.keys()
                    )
                    items.append(FileInfo(
                        path=file_path,
                        is_dir=is_dir,
                        size=len(self.files[file_path])
                    ))
        return items
    
    def download_files(self, paths: List[str]) -> List[FileDownloadResponse]:
        """Download files from memory."""
        return [
            FileDownloadResponse(
                path=path,
                content=self.files.get(path),
                error=None if path in self.files else "file_not_found"
            )
            for path in paths
        ]
    
    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[FileUploadResponse]:
        """Upload files to memory."""
        responses = []
        for path, content in files:
            self.files[path] = content
            responses.append(FileUploadResponse(path=path))
        return responses


# =============================================================================
# Agent Skills Specification Constants and Validation
# =============================================================================
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_skill_name(name: str, directory_name: str) -> Tuple[bool, str]:
    """Validate skill name per Agent Skills specification.
    
    Requirements:
    - Max 64 characters
    - Lowercase alphanumeric and hyphens only
    - Cannot start or end with hyphen
    - No consecutive hyphens
    - Must match parent directory name
    """
    if not name:
        return False, "name is required"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, "name exceeds 64 characters"
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        return False, "name must be lowercase alphanumeric with single hyphens"
    if name != directory_name:
        return False, f"name '{name}' must match directory '{directory_name}'"
    return True, ""


def parse_skill_metadata(content: str, skill_path: str, directory_name: str) -> Optional[Dict]:
    """Parse YAML frontmatter from SKILL.md content."""
    if len(content) > MAX_SKILL_FILE_SIZE:
        print(f"  [Warning] Skipping {skill_path}: content too large")
        return None
    
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if not match:
        print(f"  [Warning] Skipping {skill_path}: no valid YAML frontmatter")
        return None
    
    try:
        frontmatter_data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        print(f"  [Warning] Invalid YAML in {skill_path}: {e}")
        return None
    
    if not isinstance(frontmatter_data, dict):
        print(f"  [Warning] Skipping {skill_path}: frontmatter is not a mapping")
        return None
    
    name = frontmatter_data.get("name")
    description = frontmatter_data.get("description")
    
    if not name or not description:
        print(f"  [Warning] Skipping {skill_path}: missing 'name' or 'description'")
        return None
    
    is_valid, error = validate_skill_name(str(name), directory_name)
    if not is_valid:
        print(f"  [Warning] Skill '{name}' in {skill_path}: {error}")
    
    description_str = str(description).strip()[:MAX_SKILL_DESCRIPTION_LENGTH]
    allowed_tools = frontmatter_data.get("allowed-tools", "").split() if frontmatter_data.get("allowed-tools") else []
    
    return {
        "name": str(name),
        "description": description_str,
        "path": skill_path,
        "license": frontmatter_data.get("license", "").strip() or None,
        "compatibility": frontmatter_data.get("compatibility", "").strip() or None,
        "metadata": frontmatter_data.get("metadata", {}),
        "allowed_tools": allowed_tools,
    }


def list_skills(backend: BackendProtocol, source_path: str) -> List[Dict]:
    """List all skills from a backend source."""
    skills = []
    items = backend.ls_info(source_path)
    
    skill_dirs = [item for item in items if item.is_dir]
    if not skill_dirs:
        return []
    
    for item in skill_dirs:
        from pathlib import PurePosixPath
        skill_dir = PurePosixPath(item.path)
        skill_md_path = str(skill_dir / "SKILL.md")
        
        responses = backend.download_files([skill_md_path])
        response = responses[0]
        
        if response.error or not response.content:
            continue
        
        try:
            content = response.content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        
        directory_name = PurePosixPath(item.path).name
        skill_metadata = parse_skill_metadata(content, skill_md_path, directory_name)
        if skill_metadata:
            skills.append(skill_metadata)
    
    return skills


# =============================================================================
# Skills System Prompt Template
# =============================================================================
SKILLS_SYSTEM_PROMPT = """

## Skills System

You have access to a skills library providing specialized capabilities and domain knowledge.

{skills_locations}

**Available Skills:**

{skills_list}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern:

1. **Recognition**: Check if task matches a skill's description
2. **Reading**: Use the path to read full SKILL.md instructions
3. **Execution**: Follow the skill's step-by-step workflows
4. **Support**: Access helper scripts in skill directory

**When to Use Skills:**
- Task matches skill's domain (e.g., "research X" → web-research)
- Need structured workflows for complex tasks
- Skill provides proven patterns and best practices

Remember: Skills make you more capable and consistent!
"""


# =============================================================================
# AgentMiddleware Base Class
# =============================================================================
class AgentMiddleware(ABC, Generic[StateT, ContextT]):
    """Base middleware class for agent customization.
    
    Subclass and implement any of the defined methods to customize
    agent behavior at various points in the execution lifecycle.
    """
    
    state_schema: Type[StateT] = AgentState
    tools: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def name(self) -> str:
        """The name of the middleware instance."""
        return self.__class__.__name__
    
    # Lifecycle hooks
    def before_agent(self, state: StateT, runtime: Runtime, config: Dict) -> Optional[Dict[str, Any]]:
        return None
    
    def after_agent(self, state: StateT, runtime: Runtime, config: Dict) -> Optional[Dict[str, Any]]:
        return None
    
    def before_model(self, state: StateT, runtime: Runtime, config: Dict) -> Optional[Dict[str, Any]]:
        return None
    
    def after_model(self, state: StateT, runtime: Runtime, config: Dict) -> Optional[Dict[str, Any]]:
        return None
    
    # Interception hooks
    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelResponse:
        return handler(request)
    
    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolResponse:
        return handler(request)


# =============================================================================
# SkillsMiddleware Implementation
# =============================================================================
class SkillsMiddleware(AgentMiddleware):
    """Middleware for loading and exposing agent skills.
    
    Implements Agent Skills specification (https://agentskills.io/specification)
    with progressive disclosure, multi-source loading, and backend abstraction.
    """
    
    state_schema = SkillsState
    
    def __init__(self, backend: BackendProtocol, sources: List[str]):
        self._backend = backend
        self.sources = sources
        self.system_prompt_template = SKILLS_SYSTEM_PROMPT
    
    def _format_locations(self) -> str:
        """Format skill source locations."""
        locations = []
        for i, source_path in enumerate(self.sources):
            from pathlib import PurePosixPath
            name = PurePosixPath(source_path.rstrip("/")).name.capitalize()
            suffix = " (higher priority)" if i == len(self.sources) - 1 else ""
            locations.append(f"**{name}**: `{source_path}`{suffix}")
        return "\n".join(locations)
    
    def _format_skills_list(self, skills: List[Dict]) -> str:
        """Format skill list for system prompt."""
        if not skills:
            return "(No skills available)"
        
        lines = []
        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            if skill.get('allowed_tools'):
                lines.append(f"  -> Allowed tools: {', '.join(skill['allowed_tools'])}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")
        return "\n".join(lines)
    
    def before_agent(
        self, 
        state: SkillsState, 
        runtime: Runtime, 
        config: Dict
    ) -> Optional[Dict[str, Any]]:
        """Load skills metadata from all configured sources."""
        if state.skills_metadata is not None:
            return None
        
        all_skills: Dict[str, Dict] = {}
        for source_path in self.sources:
            source_skills = list_skills(self._backend, source_path)
            for skill in source_skills:
                all_skills[skill['name']] = skill
        
        return {"skills_metadata": list(all_skills.values())}
    
    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelResponse:
        """Inject skills documentation into system prompt."""
        skills_metadata = getattr(request, 'skills_metadata', [])
        if hasattr(request, 'state') and request.state:
            skills_metadata = request.state.get("skills_metadata", [])
        
        skills_section = self.system_prompt_template.format(
            skills_locations=self._format_locations(),
            skills_list=self._format_skills_list(skills_metadata),
        )
        
        new_prompt = (request.system_prompt or "") + "\n\n" + skills_section
        modified_request = request.override(system_prompt=new_prompt)
        return handler(modified_request)


# =============================================================================
# Decorator Helpers
# =============================================================================
def before_agent(func: Callable) -> AgentMiddleware:
    """Create middleware from a before_agent function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        before_agent = wrapper
    
    DynamicMiddleware.__name__ = func.__name__ or "BeforeAgentMiddleware"
    return DynamicMiddleware()


def after_agent(func: Callable) -> AgentMiddleware:
    """Create middleware from an after_agent function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        after_agent = wrapper
    
    DynamicMiddleware.__name__ = func.__name__ or "AfterAgentMiddleware"
    return DynamicMiddleware()


def before_model(func: Callable) -> AgentMiddleware:
    """Create middleware from a before_model function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        before_model = wrapper
    
    DynamicMiddleware.__name__ = func.__name__ or "BeforeModelMiddleware"
    return DynamicMiddleware()


def after_model(func: Callable) -> AgentMiddleware:
    """Create middleware from an after_model function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        after_model = wrapper
    
    DynamicMiddleware.__name__ = func.__name__ or "AfterModelMiddleware"
    return DynamicMiddleware()


def wrap_model_call(func: Callable) -> AgentMiddleware:
    """Create middleware from a wrap_model_call function."""
    @wraps(func)
    def wrapper(self, request, handler):
        return func(request, handler)
    
    class DynamicMiddleware(AgentMiddleware):
        wrap_model_call = wrapper
    
    DynamicMiddleware.__name__ = func.__name__ or "WrapModelCallMiddleware"
    return DynamicMiddleware()


# =============================================================================
# SimpleAgent Implementation
# =============================================================================
class SimpleAgent:
    """Simple agent implementation with middleware support and Provider integration."""
    
    def __init__(
        self,
        model_name: str = "gpt-4",
        middleware: List = None,
        max_iterations: int = 10,
        provider: BaseLLM = None
    ):
        self.model_name = model_name
        self.middleware = middleware or []
        self.max_iterations = max_iterations
        self.provider = provider
        
        if provider is not None:
            print(f"  [Info] Using Provider: {type(provider).__name__}")
    
    def _execute_hooks(
        self,
        hook_name: str,
        state: AgentState,
        runtime: Runtime,
        config: Dict,
        is_async: bool = False
    ) -> List[Dict[str, Any]]:
        """Execute middleware hooks and collect state updates."""
        updates = []
        for mw in self.middleware:
            hook_method = getattr(mw, hook_name, None)
            if hook_method and callable(hook_method):
                try:
                    result = hook_method(state, runtime, config)
                    if result:
                        updates.append(result)
                except Exception as e:
                    print(f"  [Error] {mw.name}.{hook_name}: {e}")
        return updates
    
    def _merge_state_updates(
        self,
        state: 'SkillsState',
        updates: List[Dict[str, Any]]
    ) -> 'SkillsState':
        """Merge state updates into new state."""
        new_state = SkillsState(
            messages=state.messages.copy(),
            jump_to=state.jump_to,
            structured_response=state.structured_response,
            skills_metadata=state.skills_metadata
        )
        for update in updates:
            if 'messages' in update:
                new_state.messages.extend(update['messages'])
            if 'jump_to' in update:
                new_state.jump_to = update['jump_to']
            if 'skills_metadata' in update:
                new_state.skills_metadata = update['skills_metadata']
        return new_state
    
    def _simulate_model_call(self, request: ModelRequest) -> ModelResponse:
        """Simulate a model call (replace with actual LLM)."""
        last_user_msg = ""
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        
        content = f"[{self.model_name}] '{last_user_msg}'"
        
        if request.system_prompt and "Skills System" in request.system_prompt:
            content += " (Skills available)"
        
        tool_calls = []
        if "tool" in last_user_msg.lower():
            tool_calls = [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "example_tool", "arguments": "{}"}
            }]
            content += " Using tool..."
        
        return ModelResponse(content=content, tool_calls=tool_calls)
    
    async def _real_model_call(self, request: ModelRequest) -> ModelResponse:
        """Execute actual LLM call via Provider."""
        if not self.provider:
            raise ValueError("Provider not configured. Use provider= parameter in SimpleAgent constructor.")
        
        if not PROVIDER_AVAILABLE or AssistantMessage is None:
            raise ImportError("Provider modules not available. Check imports at top of file.")
        
        try:
            assistant_messages = self._convert_messages_to_assistant_format(request.messages)
            
            if request.tools:
                tools = request.tools
            else:
                tools = None
            
            response_msg, usage = await self.provider.agenerate(
                messages=assistant_messages,
                tools=tools
            )
            
            content = response_msg.text or ""
            
            tool_calls = []
            for c in response_msg.content:
                if isinstance(c, ToolRequest):
                    tool_call = {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.tool_call.value.name,
                            "arguments": c.tool_call.value.arguments
                        }
                    }
                    tool_calls.append(tool_call)
            
            print(f"  [Usage] Input tokens: {usage.get('input_tokens', 'N/A')}, Output tokens: {usage.get('output_tokens', 'N/A')}")
            
            return ModelResponse(content=content, tool_calls=tool_calls)
            
        except Exception as e:
            print(f"  [Error] Provider call failed: {e}")
            raise
    
    def _convert_messages_to_assistant_format(self, messages: List[Dict[str, Any]]) -> List[AssistantMessage]:
        """Convert simple message dicts to Assistant Message objects."""
        result = []
        for msg in messages:
            role_str = msg.get("role", "user")
            try:
                role = Role(role_str.upper())
            except ValueError:
                role = Role.USER
            
            content = msg.get("content", "")
            if isinstance(content, str):
                text_content = TextContent(text=content)
                content = [text_content]
            
            result.append(AssistantMessage(role=role, content=content))
        return result
    
    def _chain_model_call(self, request: ModelRequest) -> ModelResponse:
        """Chain model call through middleware."""
        for mw in self.middleware:
            if hasattr(mw, 'modify_request'):
                request = mw.modify_request(request)
        
        async def real_handler(req):
            return await self._real_model_call(req)
        
        def simulate_handler(req):
            return self._simulate_model_call(req)
        
        if self.provider is not None:
            base_handler = real_handler
            print(f"  [Model] Using Provider for model call...")
        else:
            base_handler = simulate_handler
            print(f"  [Model] Using simulation for model call...")
        
        handler = base_handler
        for mw in reversed(self.middleware):
            if hasattr(mw, 'wrap_model_call') and mw.wrap_model_call is not AgentMiddleware.wrap_model_call:
                mw_wrap = mw.wrap_model_call
                def make_wrapper(prev=handler, wrap=mw_wrap):
                    def wrapper(req):
                        return wrap(req, prev)
                    return wrapper
                handler = make_wrapper()
        
        return handler(request)
    
    def _chain_tool_call(self, request: ToolCallRequest) -> ToolResponse:
        """Chain tool call through middleware."""
        def base_handler(req):
            return self._simulate_tool_call(req)
        
        handler = base_handler
        for mw in reversed(self.middleware):
            if hasattr(mw, 'wrap_tool_call') and mw.wrap_tool_call is not AgentMiddleware.wrap_tool_call:
                mw_wrap = mw.wrap_tool_call
                def make_wrapper(prev=handler, wrap=mw_wrap):
                    def wrapper(req):
                        return wrap(req, prev)
                    return wrapper
                handler = make_wrapper()
        
        return handler(request)
    
    def run(
        self,
        initial_messages: List[Dict[str, Any]],
        runtime: Runtime = None,
        config: Dict = None,
        is_async: bool = False
    ) -> 'SkillsState':
        """Run the agent with middleware."""
        if self.provider is not None and not is_async:
            import asyncio
            return asyncio.run(self._run_async(initial_messages, runtime, config))
        elif is_async:
            return asyncio.run(self._run_async(initial_messages, runtime, config))
        else:
            return self._run_sync(initial_messages, runtime, config)
    
    async def _run_async(
        self,
        initial_messages: List[Dict[str, Any]],
        runtime: Runtime = None,
        config: Dict = None
    ) -> 'SkillsState':
        """Async execution with Provider support."""
        runtime = runtime or Runtime()
        config = config or {}
        state = SkillsState(messages=initial_messages)
        
        print(f"\n{'='*60}")
        print(f"Agent: {self.model_name} (Async)")
        print(f"{'='*60}")
        
        updates = self._execute_hooks('before_agent', state, runtime, config, True)
        state = self._merge_state_updates(state, updates)
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            
            updates = self._execute_hooks('before_model', state, runtime, config, True)
            state = self._merge_state_updates(state, updates)
            
            if state.jump_to == JumpTo.END:
                print("  [Jump] Early termination")
                break
            
            request = ModelRequest(
                model_name=self.model_name,
                messages=state.messages,
                system_prompt=None
            )
            print("  [Model] Calling...")
            response = await self._chain_model_call_async(request)
            
            state.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls
            })
            
            updates = self._execute_hooks('after_model', state, runtime, config, True)
            state = self._merge_state_updates(state, updates)
            
            tool_executed = False
            for tool_call in response.tool_calls:
                tool_request = ToolCallRequest(
                    tool_name=tool_call["function"]["name"],
                    args=tool_call.get("function", {}).get("arguments", {}),
                    tool_call_id=tool_call["id"]
                )
                print(f"  [Tool] Calling {tool_request.tool_name}...")
                tool_response = self._chain_tool_call(tool_request)
                
                state.messages.append({
                    "role": "tool",
                    "content": str(tool_response.content),
                    "tool_call_id": tool_response.tool_call_id
                })
                tool_executed = True
            
            if not tool_executed:
                print("  [End] No more tool calls")
                break
            
            if state.jump_to == JumpTo.END:
                print("  [Jump] Termination requested")
                break
        
        updates = self._execute_hooks('after_agent', state, runtime, config, True)
        state = self._merge_state_updates(state, updates)
        
        print(f"\n{'='*60}")
        print("Execution complete")
        print(f"{'='*60}")
        
        return state
    
    async def _chain_model_call_async(self, request: ModelRequest) -> ModelResponse:
        """Async chain model call through middleware with Provider support."""
        for mw in self.middleware:
            if hasattr(mw, 'modify_request'):
                request = mw.modify_request(request)
        
        async def real_handler(req):
            return await self._real_model_call(req)
        
        def simulate_handler(req):
            return self._simulate_model_call(req)
        
        if self.provider is not None:
            base_handler = real_handler
            print(f"  [Model] Using Provider for model call...")
        else:
            base_handler = simulate_handler
            print(f"  [Model] Using simulation for model call...")
        
        handler = base_handler
        for mw in reversed(self.middleware):
            if hasattr(mw, 'wrap_model_call') and mw.wrap_model_call is not AgentMiddleware.wrap_model_call:
                mw_wrap = mw.wrap_model_call
                def make_wrapper(prev=handler, wrap=mw_wrap):
                    def wrapper(req):
                        return wrap(req, prev)
                    return wrapper
                handler = make_wrapper()
        
        return await handler(request)
    
    def _run_sync(
        self,
        initial_messages: List[Dict[str, Any]],
        runtime: Runtime = None,
        config: Dict = None
    ) -> 'SkillsState':
        """Synchronous execution (simulation mode)."""
        runtime = runtime or Runtime()
        config = config or {}
        state = SkillsState(messages=initial_messages)
        
        print(f"\n{'='*60}")
        print(f"Agent: {self.model_name} (Sync)")
        print(f"{'='*60}")
        
        updates = self._execute_hooks('before_agent', state, runtime, config, False)
        state = self._merge_state_updates(state, updates)
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            
            updates = self._execute_hooks('before_model', state, runtime, config, False)
            state = self._merge_state_updates(state, updates)
            
            if state.jump_to == JumpTo.END:
                print("  [Jump] Early termination")
                break
            
            request = ModelRequest(
                model_name=self.model_name,
                messages=state.messages,
                system_prompt=None
            )
            print("  [Model] Calling...")
            response = self._chain_model_call(request)
            
            state.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls
            })
            
            updates = self._execute_hooks('after_model', state, runtime, config, False)
            state = self._merge_state_updates(state, updates)
            
            tool_executed = False
            for tool_call in response.tool_calls:
                tool_request = ToolCallRequest(
                    tool_name=tool_call["function"]["name"],
                    args={},
                    tool_call_id=tool_call["id"]
                )
                print(f"  [Tool] Calling {tool_request.tool_name}...")
                tool_response = self._chain_tool_call(tool_request)
                
                state.messages.append({
                    "role": "tool",
                    "content": str(tool_response.content),
                    "tool_call_id": tool_response.tool_call_id
                })
                tool_executed = True
            
            if not tool_executed:
                print("  [End] No more tool calls")
                break
            
            if state.jump_to == JumpTo.END:
                print("  [Jump] Termination requested")
                break
        
        updates = self._execute_hooks('after_agent', state, runtime, config, False)
        state = self._merge_state_updates(state, updates)
        
        print(f"\n{'='*60}")
        print("Execution complete")
        print(f"{'='*60}")
        
        return state


# =============================================================================
# Skill Examples
# =============================================================================
SKILL_EXAMPLES = {
    "web-research": """---
name: web-research
description: Structured approach to conducting thorough web research using subagents
---
# Web Research Skill

## When to Use
Research complex topics requiring multiple information sources.

## Process
1. Create research folder: `mkdir research_[topic]`
2. Write research plan: `research_[topic]/research_plan.md`
3. Delegate to subagents
4. Synthesize findings
5. Present results
""",
    "query-writing": """---
name: query-writing
description: For writing and executing SQL queries - simple to complex JOINs
---
# Query Writing Skill

## When to Use
Need to answer questions using SQL queries.

## Workflow
1. Identify tables needed
2. Examine schemas
3. Write query (SELECT → FROM/JOIN → WHERE → GROUP BY → ORDER BY → LIMIT)
4. Execute and validate
5. Present results

## Quality Guidelines
- Query only relevant columns
- Always apply LIMIT
- Use table aliases
- Never use DML (INSERT, UPDATE, DELETE)
""",
    "code-review": """---
name: code-review
description: Systematic code review workflow for bugs, security, and quality
---
# Code Review Skill

## When to Use
Review code for bugs, security issues, or quality problems.

## Checklist
- [ ] Error handling comprehensive
- [ ] No hardcoded secrets
- [ ] Resources properly cleaned up
- [ ] Code well-documented
- [ ] Tests cover edge cases
- [ ] Performance considered

## Process
1. Understand context
2. Check common issues
3. Verify tests
4. Provide feedback
""",
}


def setup_skill_backend() -> MemoryBackend:
    """Create a backend with example skills."""
    backend = MemoryBackend()
    for name, content in SKILL_EXAMPLES.items():
        path = f"/skills/user/{name}/SKILL.md"
        backend.upload_files([(path, content.encode("utf-8"))])
    return backend


# =============================================================================
# Demo Examples
# =============================================================================
def print_conversation(state: AgentState):
    """Pretty print the conversation."""
    print("\n" + "-"*40)
    print("Conversation:")
    print("-"*40)
    for i, msg in enumerate(state.messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:80]
        print(f"{i+1}. [{role}]: {content}{'...' if len(msg.get('content', '')) > 80 else ''}")
    print("-"*40)


def example_basic_agent():
    """Example 1: Basic agent without middleware."""
    print("\n" + "#"*60)
    print("# Example 1: Basic Agent")
    print("#"*60)
    config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
    provider = ProviderFactory.create_llm("openai", config)
    agent = SimpleAgent("qwen3_vl",provider=provider)
    result = agent.run([{"role": "user", "content": "Hello, how are you?"}])
    print_conversation(result)


def example_skills_middleware():
    """Example 2: SkillsMiddleware with Agent Skills specification."""
    print("\n" + "#"*60)
    print("# Example 2: SkillsMiddleware")
    print("# Demonstrates: Agent Skills specification, progressive disclosure")
    print("#"*60)
    
    backend = setup_skill_backend()
    middleware = SkillsMiddleware(backend=backend, sources=["/skills/user/"])
    
    config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
    provider = ProviderFactory.create_llm("openai", config)
    agent = SimpleAgent("qwen3_vl",provider=provider, middleware=[middleware])
    result = agent.run([{"role": "user", "content": "I need to research quantum computing"}])
    
    print("\n[Skills Loaded]")
    if result.skills_metadata:
        for skill in result.skills_metadata:
            print(f"  - {skill['name']}: {skill['description']}")
    
    print_conversation(result)


def example_skills_override():
    """Example 3: Skills from multiple sources with override."""
    print("\n" + "#"*60)
    print("# Example 3: Multi-Source Skills with Override")
    print("# Later sources override earlier ones (last one wins)")
    print("#"*60)
    
    backend = MemoryBackend()
    backend.upload_files([
        ("/skills/base/shared-skill/SKILL.md", b"""---
name: shared-skill
description: Base version - shared skill from base source
---
# Shared Skill (Base)
This is the base version.
"""),
        ("/skills/project/shared-skill/SKILL.md", b"""---
name: shared-skill
description: Project version - overrides base version
---
# Shared Skill (Project)
This is the project version that overrides the base.
"""),
    ])
    
    middleware = SkillsMiddleware(
        backend=backend,
        sources=["/skills/base/", "/skills/project/"]
    )
    
    config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
    provider = ProviderFactory.create_llm("openai", config)
    agent = SimpleAgent("qwen3_vl",provider=provider, middleware=[middleware])
    result = agent.run([{"role": "user", "content": "What skills do you have?"}])
    
    print("\n[Loaded Skills]")
    if result.skills_metadata:
        for skill in result.skills_metadata:
            print(f"  - {skill['name']}: {skill['description']}")


def example_middleware_combination():
    """Example 4: SkillsMiddleware combined with decorator middleware."""
    print("\n" + "#"*60)
    print("# Example 4: Skills + Decorator Middleware Combination")
    print("#"*60)
    
    backend = setup_skill_backend()
    
    @before_model
    def log_timing(state, runtime, config):
        print(f"  [Timing] {len(state.messages)} messages in history")
    
    @after_model
    def log_response(state, runtime, config):
        last = state.messages[-1] if state.messages else {}
        content = last.get("content", "")[:50]
        print(f"  [Response] {content}...")
    
    middleware = [
        SkillsMiddleware(backend=backend, sources=["/skills/user/"]),
        log_timing,
        log_response,
    ]
    
    config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
    provider = ProviderFactory.create_llm("openai", config)
    agent = SimpleAgent("qwen3_vl",provider=provider, middleware=[middleware])
    result = agent.run([{"role": "user", "content": "Help me write a SQL query"}])
    print_conversation(result)


def example_skill_validation():
    """Example 5: Skill metadata validation."""
    print("\n" + "#"*60)
    print("# Example 5: Skill Metadata Validation")
    print("# Tests name validation per Agent Skills specification")
    print("#"*60)
    
    test_cases = [
        ("web-research", "web-research", True, "Valid name"),
        ("My-Skill", "My-Skill", False, "Uppercase invalid"),
        ("my--skill", "my--skill", False, "Consecutive hyphens"),
        ("skill_v2", "skill_v2", False, "Underscores invalid"),
        ("a" * 65, "a" * 65, False, "Too long (>64 chars)"),
    ]
    
    print("\n[Validation Results]")
    for name, directory, expected_valid, description in test_cases:
        is_valid, error = validate_skill_name(name, directory)
        status = "PASS" if is_valid == expected_valid else "FAIL"
        print(f"  [{status}] {description}: '{name}' -> {error or 'valid'}")


def example_all_skills():
    """Example 6: Show all available skills."""
    print("\n" + "#"*60)
    print("# Example 6: All Available Skills")
    print("#"*60)
    
    backend = setup_skill_backend()
    middleware = SkillsMiddleware(backend=backend, sources=["/skills/user/"])
    config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
    provider = ProviderFactory.create_llm("openai", config)
    agent = SimpleAgent("qwen3_vl",provider=provider, middleware=[middleware])
    
    state = SkillsState()
    updates = agent._execute_hooks('before_agent', state, Runtime(), {})
    state = agent._merge_state_updates(state, updates)
    
    print("\n[All Skills from Agent Skills Specification]")
    for skill in state.skills_metadata or []:
        print(f"\n  **{skill['name']}**")
        print(f"    Description: {skill['description']}")
        print(f"    Path: {skill['path']}")


def example_with_provider():
    """Example 7: SimpleAgent with Provider integration (real LLM calls)."""
    print("\n" + "#"*60)
    print("# Example 7: SimpleAgent with Provider Integration")
    print("# Demonstrates: Real LLM calls via Provider")
    print("#"*60)
    
    if not PROVIDER_AVAILABLE or ModelConfig is None or ProviderFactory is None:
        print("\n[Skipped] Provider modules not available")
        print("Make sure assistant module is properly installed.")
        return
    
    try:
        import openai  # Check if openai is installed
        
        config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
        provider = ProviderFactory.create_llm("openai", config)
        
        agent = SimpleAgent(
            model_name="qwen3_vl",
            provider=provider,
            max_iterations=5
        )
        
        result = agent.run([
            {"role": "user", "content": "What is the capital of France?"}
        ])
        
        print("\n[Response]")
        if result.messages:
            last_msg = result.messages[-1]
            print(f"  {last_msg.get('content', 'No content')}")
        
    except ImportError:
        print("\n[Skipped] 'openai' package not installed")
        print("Install it with: pip install openai")
    except ValueError as e:
        print(f"\n[Error] {e}")
        print("Please check your Provider configuration.")


def example_with_provider_and_skills():
    """Example 8: SimpleAgent with Provider and SkillsMiddleware."""
    print("\n" + "#"*60)
    print("# Example 8: Provider + SkillsMiddleware")
    print("# Demonstrates: Real LLM with Agent Skills")
    print("#"*60)
    
    if not PROVIDER_AVAILABLE or ModelConfig is None or ProviderFactory is None:
        print("\n[Skipped] Provider modules not available")
        return
    
    try:
        import openai  # Check if openai is installed
        
        
        backend = setup_skill_backend()
        skills_middleware = SkillsMiddleware(backend=backend, sources=["/skills/user/"])
        
        config = ModelConfig(
            model_name="qwen3_vl",
            api_key="vllm",
            base_url="http://192.168.10.180:8088/v1",
            api_key_env="OPENAI_API_KEY"
        )
        
        provider = ProviderFactory.create_llm("openai", config)
        agent = SimpleAgent("qwen3_vl",provider=provider, middleware=[skills_middleware], max_iterations=5)
    
        
        
        result = agent.run([
            {"role": "user", "content": "I need help with web research"}
        ])
        
        print("\n[Skills Loaded]")
        if result.skills_metadata:
            for skill in result.skills_metadata:
                print(f"  - {skill['name']}: {skill['description']}")
        
    except ImportError:
        print("\n[Skipped] 'openai' package not installed")
        print("Install it with: pip install openai")
    except ValueError as e:
        print(f"\n[Error] {e}")
        
    except ValueError as e:
        print(f"\n[Error] {e}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print(" AgentMiddleware and Skills Framework Demo")
    print("="*60)
    print("\nThis demo implements:")
    print("- AgentMiddleware base class with lifecycle hooks")
    print("- SkillsMiddleware (Agent Skills Specification)")
    print("- Backend protocol (pluggable storage)")
    print("- Progressive disclosure pattern")
    print("- Multi-source loading with override")
    print("- Provider integration for real LLM calls")
    print("="*60)
    
    example_basic_agent()
    example_skills_middleware()
    example_skills_override()
    example_middleware_combination()
    example_skill_validation()
    example_all_skills()
    
    print("\n" + "="*60)
    print(" Provider Integration Examples")
    print("="*60)
    example_with_provider()
    example_with_provider_and_skills()
    
    print("\n" + "="*60)
    print(" All examples completed!")
    print("="*60)
    print("\n[References]")
    print("- Agent Skills Specification: https://agentskills.io/specification")
    print("- LangChain: langchain.agents.middleware.types")
    print("- deepagents: F:\\Workspace\\learn_goose\\deepagents")
