# AgentMiddleware and Skills Framework Documentation

## Overview

The **AgentMiddleware** framework in LangChain provides a flexible, extensible architecture for customizing agent behavior through modular plugins called "middleware." These middleware components can intercept and modify various points in the agent execution lifecycle, enabling capabilities such as retry logic, logging, caching, tool filtering, and more.

The **SkillsMiddleware** from the **deepagents** project extends this architecture by implementing the [Agent Skills Specification](https://agentskills.io/specification), providing a standardized way to define, load, and manage agent capabilities as reusable "skills."

---

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Agent System Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Agent (create_agent)                         │   │
│  │                                                                      │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐              │   │
│  │  │  Middleware │──▶│  Middleware │──▶│  Middleware │──▶...        │   │
│  │  │     #1      │   │     #2      │   │     #3      │              │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘              │   │
│  │        │                 │                 │                       │   │
│  │        ▼                 ▼                 ▼                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                    Agent Loop                               │   │   │
│  │  │  before_agent → before_model → model → after_model          │   │   │
│  │  │         ↓              ↓            ↓          ↓              │   │   │
│  │  │  (repeat until no tool calls)                               │   │   │
│  │  │                    → after_agent                             │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Backend Protocol                                │   │
│  │                                                                      │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │   │
│  │  │FilesystemBackend│  │ StateBackend │  │ StoreBackend  │           │   │
│  │  │  (local disk)  │  │  (memory)    │  │ (persistent)  │           │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘           │   │
│  │                                                                      │   │
│  │  Used by: SkillsMiddleware, FilesystemMiddleware, etc.               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AgentMiddleware Base Class

### Class Definition

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Type, Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field

StateT = TypeVar('StateT')
ContextT = TypeVar('ContextT')

class AgentMiddleware(ABC, Generic[StateT, ContextT]):
    """Base middleware class for agent customization.
    
    Subclass this and implement any of the defined methods to customize
    agent behavior at various points in the execution lifecycle.
    """
    
    # State schema for this middleware (defaults to AgentState)
    state_schema: Type[StateT] = None
    
    # Additional tools provided by this middleware
    tools: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def name(self) -> str:
        """The name of the middleware instance."""
        return self.__class__.__name__
    
    # Lifecycle hooks
    def before_agent(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
        """Execute before agent starts."""
        return None
    
    def after_agent(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
        """Execute after agent completes."""
        return None
    
    def before_model(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
        """Execute before each model call."""
        return None
    
    def after_model(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
        """Execute after each model call."""
        return None
    
    # Interception hooks (wrapper pattern)
    def wrap_model_call(self, request, handler) -> Any:
        """Intercept model execution."""
        return handler(request)
    
    def wrap_tool_call(self, request, handler) -> Any:
        """Intercept tool execution."""
        return handler(request)
```

### Hook Types

#### 1. Lifecycle Hooks (Phase-based)

```python
# before_agent: Runs once at the start
def before_agent(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
    """Initialize resources, load skills, validate inputs."""
    return {"custom_field": "initialized"}

# before_model: Runs before each model invocation
def before_model(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
    """Modify context, add messages, check termination."""
    return None

# after_model: Runs after each model invocation
def after_model(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
    """Log response, validate output, enrich state."""
    return None

# after_agent: Runs once at the end
def after_agent(self, state: StateT, runtime, config) -> Optional[Dict[str, Any]]:
    """Cleanup resources, emit final events."""
    return None
```

#### 2. Interception Hooks (Wrapper-based)

```python
# wrap_model_call: Wraps the actual model call
def wrap_model_call(self, request, handler) -> ModelResponse:
    """Implement retry, caching, monitoring."""
    for attempt in range(3):
        try:
            return handler(request)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

# wrap_tool_call: Wraps the actual tool call
def wrap_tool_call(self, request, handler) -> ToolResponse:
    """Implement tool retries, logging, validation."""
    print(f"Executing: {request.tool_name}")
    result = handler(request)
    print(f"Result: {result.content}")
    return result
```

---

## State Management

### Default State Schema

```python
@dataclass
class AgentState:
    """Core state schema for all agents."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    jump_to: Optional[str] = None  # "tools", "model", "end"
    structured_response: Optional[Any] = None
```

### Custom State with Skills

```python
@dataclass
class SkillsState(AgentState):
    """State with skills support."""
    skills_metadata: Optional[List[SkillMetadata]] = None

class CustomMiddleware(AgentMiddleware[SkillsState]):
    """Middleware with custom state schema."""
    state_schema = SkillsState
    
    def before_agent(self, state: SkillsState, runtime, config) -> Dict[str, Any]:
        # Can access skills_metadata directly
        if state.skills_metadata:
            print(f"Skills available: {len(state.skills_metadata)}")
        return None
```

---

## Decorator-Based Middleware Creation

### Function Decorators

```python
from functools import wraps

def before_agent(func):
    """Create middleware from a before_agent function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        before_agent = wrapper
    
    return DynamicMiddleware()

def after_model(func):
    """Create middleware from an after_model function."""
    @wraps(func)
    def wrapper(self, state, runtime, config):
        return func(state, runtime, config)
    
    class DynamicMiddleware(AgentMiddleware):
        after_model = wrapper
    
    return DynamicMiddleware()

def wrap_model_call(func):
    """Create middleware from a wrap_model_call function."""
    @wraps(func)
    def wrapper(self, request, handler):
        return func(request, handler)
    
    class DynamicMiddleware(AgentMiddleware):
        wrap_model_call = wrapper
    
    return DynamicMiddleware()

# Usage examples
@before_agent
def init_logging(state, runtime, config):
    print(f"Agent starting with {len(state.messages)} messages")

@after_model
def log_response(state, runtime, config):
    print(f"Model responded: {state.messages[-1]['content'][:50]}...")

@wrap_model_call
def retry_middleware(request, handler):
    for i in range(3):
        try:
            return handler(request)
        except Exception:
            if i == 2:
                raise
```

---

## SkillsMiddleware (deepagents Implementation)

### Overview

**SkillsMiddleware** implements the [Agent Skills Specification](https://agentskills.io/specification), enabling agents to discover and use structured capabilities called "skills."

### Key Features

1. **Progressive Disclosure**: Skills show only metadata in prompts; full content loaded on demand
2. **Multi-source Loading**: Layered skill sources with override semantics
3. **Backend Abstraction**: Pluggable storage (Filesystem, State, Store)
4. **Namespace Isolation**: Per-assistant skill separation

### Skill Directory Structure

```
/skills/
├── base/                    # Base skills (lowest priority)
│   └── web-research/
│       ├── SKILL.md         # Required: YAML frontmatter + markdown
│       └── helper.py        # Optional: supporting files
├── user/                    # User skills
│   ├── query-writing/
│   │   └── SKILL.md
│   └── code-review/
│       └── SKILL.md
└── project/                 # Project skills (highest priority)
    └── custom-skill/
        └── SKILL.md
.md Format

``````

### SKILLmarkdown
---
name: web-research
description: Structured approach to conducting thorough web research using subagents
license: MIT
compatibility: Python 3.8+
metadata:
  author: Research Team
  version: 1.0.0
allowed-tools: read_file write_file list_files
---

# Web Research Skill

## When to Use This Skill

Use this skill when:
- User asks to research a topic
- Need to gather information from multiple sources
- Comparative analysis is required

## Research Process

### Step 1: Create Research Plan
1. Create folder: `mkdir research_[topic]`
2. Write plan: `research_[topic]/research_plan.md`

### Step 2: Delegate to Subagents
For each subtopic:
- Use task tool to spawn research subagents
- Run up to 3 in parallel

### Step 3: Synthesize Findings
1. List files: `list_files research_[topic]`
2. Read findings: `read_file research_[topic]/findings_*.md`
3. Synthesize into report

## Best Practices
- Always create a research plan first
- Limit to 3-5 subtopics maximum
- Synthesize before presenting results
```

### Skill Metadata Schema

```python
from typing import TypedDict, List, Optional, Dict

class SkillMetadata(TypedDict):
    """Metadata for a skill per Agent Skills specification."""
    
    name: str
    """Skill identifier (max 64 chars, lowercase alphanumeric and hyphens)."""
    
    description: str
    """What the skill does (max 1024 chars)."""
    
    path: str
    """Path to the SKILL.md file."""
    
    license: Optional[str]
    """License name or reference."""
    
    compatibility: Optional[str]
    """Environment requirements (max 500 chars)."""
    
    metadata: Dict[str, str]
    """Arbitrary key-value mapping."""
    
    allowed_tools: List[str]
    """Pre-approved tools (space-delimited)."""
```

### SkillsMiddleware Implementation

```python
class SkillsMiddleware(AgentMiddleware):
    """Middleware for loading and exposing agent skills.
    
    Features:
    - Progressive disclosure of skill metadata
    - Multi-source loading with override
    - Backend abstraction for storage
    """
    
    state_schema = SkillsState
    
    def __init__(
        self,
        backend: 'BackendProtocol',
        sources: List[str],
        system_prompt_template: str = None
    ):
        self._backend = backend
        self.sources = sources
        self.system_prompt_template = system_prompt_template or SKILLS_SYSTEM_PROMPT
    
    def before_agent(
        self, 
        state: SkillsState, 
        runtime, 
        config: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Load skills metadata from all configured sources.
        
        Skills are loaded in source order with later sources
        overriding earlier ones (last one wins).
        """
        # Skip if already loaded
        if state.skills_metadata is not None:
            return None
        
        all_skills: Dict[str, SkillMetadata] = {}
        
        for source_path in self.sources:
            source_skills = _list_skills(self._backend, source_path)
            for skill in source_skills:
                all_skills[skill['name']] = skill
        
        return {"skills_metadata": list(all_skills.values())}
    
    def wrap_model_call(
        self, 
        request: 'ModelRequest', 
        handler: Callable
    ) -> 'ModelResponse':
        """Inject skills documentation into system prompt.
        
        Implements progressive disclosure:
        - Only metadata (name, description, path) in prompt
        - Full SKILL.md loaded on demand via tool calls
        """
        skills_metadata = request.state.get("skills_metadata", [])
        
        # Format skills for system prompt
        skills_section = self.system_prompt_template.format(
            skills_locations=self._format_locations(),
            skills_list=self._format_skills_list(skills_metadata),
        )
        
        # Inject into system prompt
        new_system_prompt = self._inject_skills(
            request.system_prompt or "",
            skills_section
        )
        
        modified_request = request.override(system_prompt=new_system_prompt)
        return handler(modified_request)
    
    def _format_locations(self) -> str:
        """Format skill source locations."""
        locations = []
        for i, source_path in enumerate(self.sources):
            name = source_path.rstrip('/').split('/')[-1].capitalize()
            suffix = " (higher priority)" if i == len(self.sources) - 1 else ""
            locations.append(f"**{name}**: `{source_path}`{suffix}")
        return "\n".join(locations)
    
    def _format_skills_list(self, skills: List[SkillMetadata]) -> str:
        """Format skill list for system prompt."""
        if not skills:
            return "(No skills available)"
        
        lines = []
        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            if skill['allowed_tools']:
                lines.append(f"  -> Allowed tools: {', '.join(skill['allowed_tools'])}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")
        return "\n".join(lines)
```

### Skills System Prompt Template

```python
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
4. **Support**: Access helper scripts and configs in skill directory

**When to Use Skills:**
- Task matches skill's domain (e.g., "research X" → web-research)
- Need structured workflows for complex tasks
- Skill provides proven patterns and best practices
"""
```

### Backend Protocol

```python
from abc import ABC
from typing import List, Protocol

class FileInfo(TypedDict):
    path: str
    is_dir: Optional[bool]
    size: Optional[int]

class FileDownloadResponse(TypedDict):
    path: str
    content: Optional[bytes]
    error: Optional[str]

class BackendProtocol(ABC):
    """Protocol for pluggable skill storage backends."""
    
    def ls_info(self, path: str) -> List[FileInfo]:
        """List directory contents."""
        ...
    
    def download_files(self, paths: List[str]) -> List[FileDownloadResponse]:
        """Download skill files."""
        ...
    
    def upload_files(self, files: List[tuple[str, bytes]]) -> List[FileUploadResponse]:
        """Upload skill files."""
        ...
```

#### Available Backends

| Backend | Storage | Use Case |
|---------|---------|----------|
| FilesystemBackend | Local filesystem | Development, file-based workflows |
| StateBackend | In-memory (per conversation) | Ephemeral state, testing |
| StoreBackend | Persistent (with namespace) | Multi-tenant, production |

---

## Execution Flow

### Agent Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Agent Execution Flow                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. AGENT START                                                          │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ create_agent(model, tools, middleware=[...])                 │     │
│     │ - Initialize middleware stack                               │     │
│     │ - Merge tools from all middleware                          │     │
│     │ - Build state schema from middleware                      │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│  2. BEFORE_AGENT (once)                                                  │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ for middleware in order:                                   │     │
│     │   middleware.before_agent(state, runtime, config)         │     │
│     │   → Can modify state, load skills                        │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│  3. MODEL LOOP (repeat until no tool calls)                             │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ 3a. BEFORE_MODEL (in order)                               │     │
│     │     middleware.before_model(state, runtime, config)        │     │
│     │     → Can modify state, add context                       │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ 3b. WRAP_MODEL_CALL (build handler chain)                 │     │
│     │     M1.wrap → M2.wrap → M3.wrap → Core Model              │     │
│     │     → Can modify request, implement retries/caching       │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ 3c. Model Response                                        │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ 3d. AFTER_MODEL (in reverse order)                         │     │
│     │     middleware.after_model(state, runtime, config)         │     │
│     │     → Can log, validate, enrich state                     │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ 3e. Tool Execution (if tool calls in response)             │     │
│     │     for each tool_call:                                    │     │
│     │       M1.wrap_tool → M2.wrap_tool → Core Tool             │     │
│     │       → Can log, retry, validate                          │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                          ┌─────────┴─────────┐                           │
│                          │ More tool calls?  │                           │
│                          └─────────┬─────────┘                           │
│                     YES ─────────────┘ NO │                               │
│                                    │                                      │
│                          (repeat model loop)                             │
│                                    │                                      │
│                                    ▼                                      │
│  4. AFTER_AGENT (once, reverse order)                                    │
│     ┌──────────────────────────────────────────────────────────────┐     │
│     │ for middleware in reverse:                                 │     │
│     │   middleware.after_agent(state, runtime, config)          │     │
│     │   → Can cleanup, emit final events                        │     │
│     └──────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│  5. RETURN RESULT                                                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Middleware Composition

```python
# Middleware are composed with first one as OUTERMOST
middleware = [
    RetryMiddleware(max_retries=3),    # Outermost: wraps everything
    LoggingMiddleware(),               # Middle: wraps inner
    SkillsMiddleware(backend, sources),# Inner: closest to core
    CachingMiddleware(),               # Closest to core
]

# Execution order:
# Retry → Logging → Skills → Caching → Model
```

---

## Complete Example

```python
from typing import List, Dict, Any

# 1. Define custom middleware
class LoggingMiddleware(AgentMiddleware):
    """Log all model and tool calls."""
    
    def before_model(self, state, runtime, config):
        print(f"[Log] Model call with {len(state.messages)} messages")
    
    def after_model(self, state, runtime, config):
        last_msg = state.messages[-1]
        print(f"[Log] Model responded: {last_msg['content'][:50]}...")

class RetryMiddleware(AgentMiddleware):
    """Retry failed model calls."""
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def wrap_model_call(self, request, handler):
        for attempt in range(self.max_retries):
            try:
                return handler(request)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                print(f"[Retry] Attempt {attempt + 1} failed, retrying...")

# 2. Create skills
SKILL_EXAMPLES = {
    "web-research": """---
name: web-research
description: Structured approach to conducting thorough web research
---
# Web Research Skill

## When to Use
Research complex topics requiring multiple information sources.

## Process
1. Create research folder
2. Write research plan
3. Delegate to subagents
4. Synthesize findings
""",
}

# 3. Setup skills backend
backend = MemoryBackend()
for name, content in SKILL_EXAMPLES.items():
    backend.upload_files([(f"/skills/user/{name}/SKILL.md", content.encode())])

# 4. Create middleware stack
middleware = [
    LoggingMiddleware(),
    SkillsMiddleware(backend=backend, sources=["/skills/user/"]),
    RetryMiddleware(max_retries=2),
]

# 5. Create and run agent
agent = SimpleAgent(
    model_name="gpt-4",
    middleware=middleware,
    max_iterations=10
)

result = agent.run(
    messages=[{"role": "user", "content": "Research quantum computing"}],
    runtime=Runtime(),
    config={"metadata": {"assistant_id": "researcher"}}
)

print(f"Result: {result.messages[-1]['content']}")
```

---

## Best Practices

### Middleware Development

1. **Single Responsibility**: Each middleware should do one thing well
2. **Handle Errors Gracefully**: Don't let exceptions propagate unexpectedly
3. **Support Async**: Implement both sync and async methods for flexibility
4. **Use Decorators for Simple Cases**: `@before_model`, `@after_model` are cleaner
5. **Document Behavior**: Explain what your middleware does

### Skill Development (Agent Skills Specification)

1. **Follow Naming Conventions**: `lowercase-alphanumeric-hyphens`, max 64 chars
2. **Write Clear Descriptions**: Max 1024 chars, explain when to use
3. **Provide Workflows**: Step-by-step instructions with examples
4. **Use YAML Frontmatter**: Required: name, description
5. **Include Allowed Tools**: Specify pre-approved tools if restricted
6. **Add Licensing**: Include license reference when applicable

---

## Summary

| Component | Purpose |
|-----------|---------|
| AgentMiddleware | Base class for agent customization hooks |
| before_agent | Initialize resources, load skills |
| before_model | Modify context, add messages |
| wrap_model_call | Intercept model calls (retry, cache) |
| after_model | Log, validate, enrich state |
| after_agent | Cleanup, emit final events |
| SkillsMiddleware | Load and expose Agent Skills |
| BackendProtocol | Pluggable storage abstraction |

The combination of AgentMiddleware and SkillsMiddleware provides a powerful, extensible foundation for building sophisticated agent systems with modular, maintainable components.

**References:**
- Agent Skills Specification: https://agentskills.io/specification
- LangChain AgentMiddleware: `langchain.agents.middleware.types`
- deepagents: `F:\Workspace\learn_goose\deepagents`
