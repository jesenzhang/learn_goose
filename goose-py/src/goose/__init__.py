# src/goose/__init__.py
# 可以在这里暴露常用的类，方便外部使用 `import goose`
from .model import ModelConfig
from .session import SessionManager, Session
from .conversation import Message, Conversation
from .providers import Provider, ProviderUsage, Usage,OpenAIProvider
from .agent import Agent
from .tools import Tool, ToolError, ToolRegistry
from .prompts import PromptManager

__version__ = "0.1.0"