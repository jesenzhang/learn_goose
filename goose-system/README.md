# Goose-System

Python implementation of AI Agent framework inspired by Goose-Rs.

## Overview

A modular, extensible AI Agent framework with support for:
- **Skills System**: Progressive disclosure pattern for agent capabilities
- **Tool System**: Safe tool execution with inspection layers
- **Provider Integration**: Multiple LLM providers (OpenAI, Anthropic, etc.)
- **Extension System**: MCP protocol support
- **Event Stream**: Real-time event handling

## Architecture

```
goose-system/
├── src/goose/
│   ├── agent/          # Core Agent, Reply loop, State, Events
│   ├── skills/         # Skill system (loader, registry, base)
│   ├── tools/          # Tool system (base, executor, inspection)
│   ├── providers/      # Provider integration layer
│   ├── conversation/   # Message and Conversation management
│   ├── extension/      # Extension management
│   └── security/       # Security inspection
├── tests/
├── pyproject.toml
└── README.md
```

## Features

### 1. Agent Core
- State management with SkillsState
- Reply loop with streaming support
- Event system for real-time updates
- Session management

### 2. Skills System
- Progressive disclosure pattern
- Multi-source loading with override
- YAML frontmatter metadata
- Tool extraction from skills

### 3. Tool System
- Base Tool definition (OpenAI compatible)
- Tool executor with handlers
- Inspection layers:
  - SecurityInspector
  - PermissionInspector
  - RepetitionInspector

### 4. Provider Integration
- Wraps assistant module Providers
- Support for OpenAI, Anthropic, etc.
- Streaming support
- Usage tracking

### 5. Security
- Prompt injection detection
- Dangerous pattern blocking
- Permission levels
- Repetition detection

## Usage

```python
from goose import Agent, AgentConfig
from goose.providers import create_provider

# Create provider
provider = create_provider("openai", {
    "model_name": "gpt-4",
    "api_key": "your-key"
})

# Create agent
agent = Agent(provider, AgentConfig(
    system_prompt="You are a helpful assistant."
))

# Add tools
agent.register_tool(my_tool)

# Load skills
agent.load_skill("skills/web-research")

# Chat
import asyncio
async def main():
    async for event in agent.reply_stream("Help me research AI"):
        print(event)
    state = await agent.reply("What is 2+2?")

asyncio.run(main())
```

## Skill Format

Skills use YAML frontmatter with markdown content:

```markdown
---
name: web-research
description: Structured web research workflow
allowed-tools: read_file write_file search
---
# Web Research Skill

## When to Use
Use for research tasks...

## Process
1. Create plan
2. Gather sources
3. Synthesize
```

## Events

```python
from goose.agent import AgentEvent, AgentEventType

# Listen to events
agent.event_stream.emitter.on(AgentEventType.TOOL_START, lambda e: print(f"Tool: {e}"))
```

## License

MIT

