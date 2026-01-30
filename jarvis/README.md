# Jarvis - Event-Sourced Agent Runtime

A production-grade Agent Runtime following the architecture in `docs/ARCHITECTURE.md`.

## Features

- **Event Sourcing**: All state is reconstructible from events
- **Pure Reducers**: Agent logic has no side effects
- **Effect-Based Execution**: Side effects are separated from logic
- **Async/Concurrent**: Non-blocking execution with parallel effects
- **Replayability**: Full event replay and time travel
- **LLM Providers**: OpenAI-compatible LLM integration
- **Skill System**: Dynamic skill loading and activation
- **Intent Recognition**: LLM-based intent planning
- **Conversation Management**: Full message history with visibility controls

## Architecture

```
┌─────────────────────────────────────────────┐
│                 Control Plane               │
│  (API / UI / Scheduler / Config / Admin)   │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│               Agent Runtime Core             │
│                                             │
│  ┌───────────┐   ┌─────────────────────┐  │
│  │ Event Bus │◄──►│   Execution Engine  │  │
│  └───────────┘   │ (Async / Concurrent)│  │
│        ▲          └──────────┬──────────┘  │
│        │                     │             │
│  ┌─────────────┐      ┌───────────────┐   │
│  │ State Store │◄────►│ Agent FSM     │   │
│  │ (Snapshot + │      │ (Pure Logic)  │   │
│  │  Event Log) │      └───────────────┇   │
│        ▲                                   │
│        │                                   │
│  ┌──────────────┐   ┌──────────────────┐ │
│└──►│ Replay Engine│   │ Failure Manager  │ │
│     └──────────────┘   └──────────────────┘ │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│              Capability Plane               │
│                                             │
│  Tools | MCP | Skills | SubAgents | Human  │
│  (全部是"可失败外部系统")                  │
└─────────────────────────────────────────────┘
```

## Installation

```bash
# From project root
pip install -e .
```

Or with optional dependencies:

```bash
pip install -e ".[openai,sqlite]"
```

## Quick Start

```bash
# Run the demo
python -m jarvis_core

# Or
jarvis
```

## Core Concepts

### Event

Immutable facts that describe everything that happens:

```python
event = Event.new(
    session_id="session_123",
    agent_id="my_agent",
    run_id="run_456",
    type="user_input",
    payload={"message": "Hello Jarvis!"},
)
```

### Agent (Pure Reducer)

```python
class MyAgent(Agent):
    def reduce(self, state: AgentState, event: Event):
        if event.type == "user_input":
            new_state = AgentState(...)
            effects = [llm_generate_effect(...)]
            return new_state, effects
        return state, []
```

### Runtime

```python
runtime = create_runtime(
    agent=my_agent,
    config={
        "executor": "openai",
        "llm": {
            "type": "openai",
            "config": {
                "api_key": "...",
                "base_url": "...",
            }
        }
    }
)

handle = await runtime.run(
    session_id="session_123",
    input_event=input_event,
)
```

### Event Replay

```python
# Replay from store
events = await runtime.replay(
    session_id="session_123",
    run_id="run_456",
    mode="dry_run",  # Only replay, don't execute effects
)

# Inspect events
for event in events:
    print(f"{event.type}: {event.payload}")
```

## Project Structure

```
jarvis/
├── jarvis_core/           # Core runtime library
│   ├── core/             # Event, State, Effect, Agent
│   ├── store/            # EventStore, StateStore, SnapshotManager
│   ├── executor/         # EffectExecutor, LLMExecutor
│   ├── runtime.py         # Main Runtime engine
│   ├── providers/         # LLM providers (from assistant)
│   ├── conversation/      # Message models (from assistant)
│   ├── skills/           # Skill system (from assistant)
│   └── intent/           # Intent recognition (from assistant)
│
├── examples/              # Demo scripts
│   ├── demo.py            # Main demo
│   └── full_assistant_agent.py
│
├── tests/                 # Test suite
├── docs/                  # Architecture docs
├── pyproject.toml          # Project config
└── README.md
```

## Implementation Status

- [x] Core Event module
- [x] EventStore (Memory + SQLite)
- [x] StateStore (Memory + SQLite)
- [x] Effect and Executor
- [x] Agent (Simple + ToolUsing)
- [x] Runtime (scheduling engine)
- [x] LLM Provider (from assistant)
- [x] Conversation and Message (from assistant)
- [x] Skill system (from assistant)
- [x] Intent recognition (from assistant)
- [x] Full Assistant Agent example
- [x] Demo and tests

## Next Steps

1. Add full test coverage
2. Implement API layer (FastAPI)
3. Add MCP integration
4. Implement workflow/DAG engine
5. Add more LLM providers
6. Implement distributed event store (Kafka/Redis)

## License

MIT
