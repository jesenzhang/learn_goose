# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Environment

**Important**: This project uses conda environment `base` with Python at:
```
D:\miniforge3\python.exe
```
或者
```
D:\conda\envs\agent\python.exe
```

When running Python commands, use:
```bash
"D:\miniforge3\python.exe" <script>
```
或者
```bash
"D:\conda\envs\agent\python.exe" <script>
```

Or activate conda base environment first:
```bash
conda activate base
python <script>
```

## Project Overview

This repository contains:

1. **`goose-py/`** - Python workflow-based agent framework (DAG execution, components)
2. **`goose-rs/`** - Rust implementation (Cargo workspace)
3. **`skill_micro_agent/`** - Anthropic-compatible skill-based agent service
4. **`pho/`** - **NEW unified framework** merging goose-py and skill_micro_agent
5. **Root-level scripts** - Various standalone agent implementations

### Pho - Unified Framework (NEW)

**Location**: `pho/`

Pho is the merged framework combining the best of both projects:
- **From skill_micro_agent**: Anthropic-compatible skills, intent recognition, artifact support, hot reload
- **From goose-py**: DAG workflow engine, component system, resource management

**Structure**:
```
pho/
├── src/pho/
│   ├── conversation/     # Message models (from skill_micro_agent)
│   ├── providers/        # LLM providers (from skill_micro_agent)
│   ├── agent/           # Unified agent (planned)
│   ├── skills/          # Skill system (from skill_micro_agent)
│   ├── intent/          # Intent recognition (from skill_micro_agent)
│   ├── workflow/        # DAG engine (from goose-py)
│   ├── components/      # Component system (from goose-py)
│   └── main.py          # Entry point
├── pyproject.toml
└── tests/
```

**Installation**:
```bash
cd pho
pip install -e .
```

**Usage**:
```bash
# Run test
python -m pho.main

# Or using console script
pho
```

## Repository Structure

### Rust Workspace (`goose-rs/`)

A Cargo workspace containing multiple crates:
- `goose` - Core library
- `goose-cli` - Command-line interface
- `goose-mcp` - MCP protocol implementation
- `goose-server` - Server components
- `goose-bench` - Benchmarking
- `goose-test` - Test utilities

### Python Package (`goose-py/`)

Source layout under `src/goose/`:
- `agent/` - Core agent with `Agent` and `AgentStatus`
- `workflow/` - DAG graph engine (`Graph`, `Node`, `Edge`)
- `components/` - Component library for workflow nodes
- `toolkit/` - Tool integration with MCP adapters
- `providers/` - LLM provider abstractions
- `conversation/` - Message and session management
- `sandbox/` - Code execution (Docker, native)
- `truncation/` - Token management
- `events/` - Event system
- `resources/` - Resource management

### Skill Micro Agent (`skill_micro_agent/`)

Anthropic-compatible agent service:
- FastAPI-based server
- SKILL.md + scripts/ based skill loading
- Intent recognition and routing
- Artifact support (charts, tables)
- Human-in-the-loop approval workflow

## Development Commands

### Python (conda base environment)

```bash
# Activate conda base
conda activate base

# Install pho in development mode
cd pho
pip install -e .

# Run pho test
python -m pho.main

# Install goose-py
cd goose-py
pip install -e .

# Run tests
pytest

# Run with async support
pytest tests/test_agent_resume.py -v

# Install dev dependencies
pip install pytest pytest-asyncio black isort
```

### Rust

```bash
cd goose-rs
cargo build
cargo test
cargo run -p goose-cli -- --help
cargo check
cargo fmt
cargo clippy
```

## Architecture

### Pho Unified Framework

**Key Integrations**:
1. **Tool Registry Unification** - Supports both decorator-based (`@register_tool`) and skill-based (SKILL.md) tool loading
2. **Agent ↔ Workflow Bridge** - Agents can trigger workflows; workflows can invoke agent skills
3. **Event System Merger** - Combines event types from both projects

**Shared Modules** (copied from skill_micro_agent):
- `conversation/` - Better Pydantic validation with `populate_by_name=True`
- `providers/` - Separated ConnectionConfig/InferenceConfig

**Modules from goose-py** (to be integrated):
- `workflow/` - DAG execution engine
- `components/` - Component ecosystem
- `session/` - Multi-type session management

### Workflow Engine (goose-py)

DAG-based execution:
- **Graph** - Adjacency list storage for nodes/edges
- **Node** - Stateless component + dynamic configuration
- **Edge** - Conditional routing via `source_handle`
- **WorkflowContext** - Execution context

### Component System (goose-py)

Built-in components:
- Basic: Entry, Exit, Variable Assigner
- Code: Code Runner, Lambda
- Control: Loop, Batch, Selector
- AI: LLM, Intent Detector
- Data: HTTP Requester, JSON handling

### Skill System (skill_micro_agent)

Anthropic-compatible format:
```
agent_skills/skill_name/
├── SKILL.md          # Metadata (name, type, allowed-tools)
└── scripts/          # Python functions
```

Skill types:
- `global` - Always available
- `contextual` - Requires activation

### Provider System

Multi-registry factory:
```python
# LLM
llm = ProviderFactory.create_llm("openai", config)

# Embedding
embedding = ProviderFactory.create_embedding("tei", config)

# Reranker
reranker = ProviderFactory.create_reranker("openai", config)
```

Supported providers:
- LLM: `openai`
- Embedding: `openai`, `tei`, `custom_json`
- Reranker: `tei`, `openai`, `cohere`

## Key Design Patterns

1. **Component-Node Separation** - Components define behavior; Nodes hold config
2. **Registry Pattern** - Central registration for components, tools, skills
3. **Builder Pattern** - Providers and resources
4. **Event-Driven** - Streaming output via events
5. **Adapter Pattern** - Format conversion (VueFlow)
6. **Factory Pattern** - Provider instantiation
7. **Hot Reload** - Config changes without restart (skill_micro_agent)

## Root-Level Scripts

- `micro_agent.py`, `skill_micro_agent.py` - Micro agent implementations
- `ad_micro_agent.py`, `ad_micro_client.py` - Ultra MicroAgent with Streamlit
- `skill_loader.py` - Dynamic skill loading
- `api_client.py`, `embedding_client.py`, `rerank_client.py` - API utilities

## Configuration

- Python uses `asyncio_mode = "auto"` for pytest
- Packages use source layout (`src/` directory)
- API keys via `.env` file or environment variables
- Pho config: `pho_config.yaml` (unified YAML format)

## Migration Notes

**Original projects remain unchanged** - all files are COPIED to pho, not moved.
- `goose-py` - Can still be used independently
- `skill_micro_agent` - Can still be used independently
- `pho` - New unified framework
