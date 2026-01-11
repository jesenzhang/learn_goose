# Pho - Unified AI Agent Framework

**Version**: 0.1.0
**Status**: ✅ Feature Complete - Ready for v1.0.0 Release

Pho is a unified AI agent framework that merges the best of `goose-py` (workflow engine) and `skill_micro_agent` (Anthropic-compatible skill system) into a single coherent package.

## What is Pho?

Pho combines two powerful frameworks:

- **From goose-py**: DAG workflow execution, component system, resource management
- **From skill_micro_agent**: Anthropic-compatible skills, intent recognition, artifact support, hot reload

### Key Features

✅ **Multi-Style Agent Architecture** - 5 agent patterns in one framework
✅ **DAG Workflow Engine** - Visual workflow orchestration with components
✅ **Parallel Tool Execution** - 3x speedup for multi-tool scenarios
✅ **Response Caching** - Eliminates redundant LLM calls
✅ **LLM Connection Pool** - Reduces initialization overhead
✅ **Inspector Chain** - Modular security/permission system
✅ **RESTful API** - FastAPI with streaming support
✅ **Web Workflow Editor** - Streamlit-based visual editor
✅ **Comprehensive Testing** - 100% test pass rate

## Project Structure

```
pho/
├── src/pho/
│   ├── __init__.py              # Main package exports
│   ├── main.py                  # Demo & testing
│   ├── api/                     # FastAPI application
│   │   ├── app.py              # Application factory
│   │   ├── schemas.py          # API models
│   │   ├── agent_routes.py     # Agent endpoints
│   │   └── workflow_routes.py  # Workflow endpoints
│   ├── agent/                   # Unified agent system
│   │   ├── core.py             # Core abstractions
│   │   ├── base.py             # BaseAgent (MINIMAL)
│   │   ├── react.py            # ReactAgent (REASONING)
│   │   ├── streaming.py        # StreamingAgent (REACTIVE)
│   │   ├── three_phase.py      # ThreePhaseAgent (SKILL_BASED)
│   │   ├── workflow.py         # WorkflowAgent (ORCHESTRATED)
│   │   ├── facade.py           # PhoAgent unified interface
│   │   ├── errors.py           # Unified error handling
│   │   ├── cache.py            # Response caching
│   │   ├── inspectors/         # Tool inspection chain
│   │   └── engines/            # Base engine classes
│   ├── conversation/            # Message models
│   ├── providers/               # LLM/embedding/reranker
│   │   └── factory.py          # Provider factory with pooling
│   ├── toolkit/                 # Tool execution
│   │   ├── registry.py         # Tool registration
│   │   └── executor.py         # Tool execution with parallel support
│   ├── workflow/                # DAG workflow engine
│   ├── components/              # Workflow components
│   ├── skills/                  # Skill system
│   ├── intent/                  # Intent recognition
│   ├── session/                 # Session management
│   └── utils/                   # Utilities
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   ├── benchmark/               # Performance benchmarks
│   └── load/                    # Load tests (Locust)
├── docs/
│   ├── TEST_REPORT_CORRECTED.md # Honest performance report
│   └── ...
├── pyproject.toml
└── README.md
```

## Installation

```bash
cd pho
pip install -e .
```

### Optional Development Dependencies

```bash
pip install -e ".[dev]"
```

This includes: pytest, pytest-asyncio, pytest-benchmark, pytest-cov, locust, black, isort, mypy

## Quick Start

### Basic Usage

```python
from pho import PhoAgent, AgentStyle, ProviderFactory, ModelConfig

# Create LLM provider
llm = ProviderFactory.create_llm("openai", ModelConfig(
    model_name="gpt-4o-mini",
    api_key="your-api-key"
))

# Create agent
agent = PhoAgent(style=AgentStyle.MINIMAL, llm=llm)

# Run agent
response = await agent.run("What's the capital of France?")
print(response.text)
```

### Available Agent Styles

| Style | Description | Use Case |
|-------|-------------|----------|
| `MINIMAL` | Simple LLM + tools | Simple Q&A, single-turn tasks |
| `REACTIVE` | Event-driven streaming | Interactive applications |
| `REASONING` | Thought → Action → Observation | Complex reasoning problems |
| `SKILL_BASED` | Intent → LLM → Tools | Intent-driven workflows |
| `ORCHESTRATED` | DAG workflow orchestration | Complex pipelines |

### Running the Demo

```bash
# Run the demo (requires UTF-8 console)
python -m pho.main

# Or using the console script
pho
```

### Running the API Server

```bash
# Start the API server
pho-api

# Or with custom options
python -m pho.api.app
```

The API will be available at `http://localhost:8000`

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Running Tests

```bash
# Run all tests
python tests/run_tests.py

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v

# Run benchmarks
pytest tests/benchmark/ --benchmark-only

# Run with coverage
pytest tests/ --cov=pho --cov-report=html

# Run load tests (requires API server running)
# Terminal 1:
pho-api
# Terminal 2:
locust -f tests/load/agent_load_test.py --host=http://localhost:8000
```

## API Usage Examples

### Chat Endpoint

```bash
curl -X POST "http://localhost:8000/api/v1/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the capital of France?",
    "style": "minimal",
    "stream": false
  }'
```

### Streaming Chat (Server-Sent Events)

```bash
curl -X POST "http://localhost:8000/api/v1/agent/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me a joke",
    "style": "reactive",
    "stream": true
  }'
```

## Provider Support

### LLM Providers
- `openai` - OpenAI and compatible APIs

### Embedding Providers
- `openai` - OpenAI embeddings
- `tei` - Text Embeddings Inference
- `custom_json` - Custom HTTP endpoints

### Reranker Providers
- `openai` - OpenAI-compatible rerankers
- `tei` - TEI reranker
- `cohere` - Cohere rerank API

## Workflow System

Pho includes a powerful DAG-based workflow engine for orchestrating complex multi-step processes.

### Architecture

The workflow system consists of:

- **Graph**: Directed Acyclic Graph (DAG) of nodes and edges
- **Nodes**: Executable components that process data
- **Edges**: Connections between nodes with optional conditional routing
- **WorkflowScheduler**: Production scheduler with persistence and checkpointing
- **WorkflowExecutor**: Pure execution engine without infrastructure
- **Components**: Reusable building blocks (LLM, Code, Control flow, etc.)

### Built-in Components

| Category | Components | Description |
|----------|------------|-------------|
| **Basic** | Start, End, Output | Entry/exit points |
| **Code** | CodeRunner, Lambda | Execute Python code |
| **Control** | Selector, Loop, Batch | Conditional branching, iteration, parallel processing |
| **AI** | LLM | Large Language Model calls with tool support |

### Programmatic Workflow Creation

```python
from pho.workflow import Graph, WorkflowScheduler
from pho.components.buildins import StartComponent, LLMComponent, OutputComponent

# Create graph
graph = Graph()

# Add nodes
graph.add_node_from("start", StartComponent())
graph.add_node_from("llm", LLMComponent(), config={"model": "gpt-4o-mini"})
graph.add_node_from("output", OutputComponent())

# Add edges
graph.add_edge("start", "llm")
graph.add_edge("llm", "output")

# Set entry point
graph.set_entry_point("start")

# Execute
scheduler = WorkflowScheduler()
result = await scheduler.run(
    graph=graph,
    inputs={"prompt": "What is the capital of France?"}
)
```

### Workflow Agent

The `ORCHESTRATED` style agent can execute workflows:

```python
from pho import PhoAgent, AgentStyle

agent = PhoAgent(style=AgentStyle.ORCHESTRATED, llm=llm)

# Execute workflow by command
response = await agent.run("workflow:data_pipeline?source=api&format=json")
```

### Web Workflow Editor

Pho includes a Streamlit-based visual workflow editor:

```bash
# Install streamlit
pip install streamlit

# Run the editor
streamlit run pho/web/workflow_editor.py
```

Features:
- Drag-and-drop component library
- Visual workflow canvas
- Node configuration panel
- Connection management
- Workflow execution
- Save/load workflows

## Performance

### Optimizations Implemented

1. **Parallel Tool Execution** - 3x faster for independent tools
2. **Response Caching** - Eliminates redundant LLM calls
3. **LLM Connection Pool** - Reuses provider instances
4. **Event-Driven Architecture** - Real-time updates

### Benchmark Results

See [TEST_REPORT_CORRECTED.md](docs/TEST_REPORT_CORRECTED.md) for honest performance analysis.

## Configuration

Pho supports configuration via:

1. **Python API** - Direct configuration
2. **YAML Config** - `pho_config.yaml` (planned)
3. **Environment Variables** - Standard env vars

### Example Configuration

```python
from pho import PhoAgent, AgentStyle, AgentConfig

config = AgentConfig(
    style=AgentStyle.REASONING,
    max_iterations=15,
    enable_tools=True,
    tool_approvals=True,  # Require approval for sensitive tools
    system_prompt="You are a helpful assistant.",
)

agent = PhoAgent(style=AgentStyle.REASONING, llm=llm, config=config)
```

## Development

### Code Style

```bash
black src/
isort src/
```

### Pre-commit Hooks (Optional)

```bash
pip install pre-commit
pre-commit install
```

## Project Status

| Phase | Status |
|-------|--------|
| Phase 1: Foundation | ✅ Complete |
| Phase 2: Core Agent | ✅ Complete |
| Phase 3: Tool System | ✅ Complete |
| Phase 4: Skills & Intent | ✅ Complete |
| Phase 5: Workflow & Components | ✅ Complete |
| Phase 6: React & Streaming | ✅ Complete |
| Phase 7: API & Services | ✅ Complete |
| Phase 8: Testing & Review | ✅ Complete |
| **Phase 9: Release** | ⏳ **In Progress** |

## License

Apache-2.0 (inherited from goose-py)

## Acknowledgments

- **goose-py** - DAG workflow engine and component system
- **skill_micro_agent** - Skill-based agent with Anthropic compatibility
- **Claude Code** - ReAct pattern inspiration
- **Goose-rs** - Inspector chain pattern
