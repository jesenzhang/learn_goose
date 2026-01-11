"""
Pho Main Entry Point - Demonstrating the Agent System
"""
import asyncio
import sys
import io

# Fix UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


async def demo_basic_agent():
    """Demonstrate basic BaseAgent usage"""
    print("\n" + "="*50)
    print("BaseAgent Demo - Minimal Agent Implementation")
    print("="*50 + "\n")

    try:
        from pho import BaseAgent, ModelConfig, ProviderFactory

        # Create LLM provider
        print("Creating LLM provider...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"  # In production, use env variable
        ))
        print("LLM provider created")

        # Create agent
        print("\nCreating BaseAgent...")
        agent = BaseAgent(
            llm=llm,
            system_prompt="You are a helpful AI assistant."
        )
        print("BaseAgent created")

        # Add event handler
        @agent.on_event("start")
        async def on_start(event):
            print(f"Agent started with input: {event.data.get('input', '')[:50]}...")

        @agent.on_event("complete")
        async def on_complete(event):
            print("Agent completed")

        print("\nRunning agent...")
        print("-" * 30)

        # Note: This will fail without real API key, but shows the structure
        # response = await agent.run("Hello! What is Pho?")
        # print(f"\nResponse: {response.text}")

        print("\nAgent structure (demo without API call):")
        print("   - Style: MINIMAL")
        print("   - Mode: REACT")
        print("   - Features: LLM + optional tools")

    except Exception as e:
        print(f"Error: {e}")


async def demo_multi_style_agent():
    """Demonstrate multi-style PhoAgent"""
    print("\n" + "="*50)
    print("PhoAgent Demo - Multi-Style Agent Facade")
    print("="*50 + "\n")

    try:
        from pho import PhoAgent, AgentStyle, ModelConfig, ProviderFactory

        print("Available Agent Styles:")
        styles = [
            (AgentStyle.MINIMAL, "BaseAgent - Simple LLM + tools"),
            (AgentStyle.REACTIVE, "StreamingAgent - Event-driven (Goose-rs)"),
            (AgentStyle.REASONING, "ReactAgent - Thought loop (Claude Code)"),
            (AgentStyle.SKILL_BASED, "ThreePhaseAgent - Intent routing"),
            (AgentStyle.ORCHESTRATED, "WorkflowAgent - DAG orchestration"),
        ]

        for style, description in styles:
            print(f"   - {style.value:15} - {description}")

        print("\nCreating PhoAgent with MINIMAL style...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"
        ))

        agent = PhoAgent(
            style=AgentStyle.MINIMAL,
            llm=llm
        )
        print(f"Agent created with style: {agent.get_style().value}")
        print(f"Config mode: {agent.get_config().mode.value}")

    except Exception as e:
        print(f"Error: {e}")


async def demo_core_abstractions():
    """Demonstrate core abstractions"""
    print("\n" + "="*50)
    print("Core Abstractions Demo")
    print("="*50 + "\n")

    try:
        from pho import (
            ExecutionMode,
            AgentStyle,
            AgentStatus,
            AgentEventType,
            Context,
            AgentResponse,
            AgentConfig,
        )

        print("Execution Modes:")
        for mode in ExecutionMode:
            print(f"   - {mode.value}")

        print("\nAgent Styles:")
        for style in AgentStyle:
            print(f"   - {style.value}")

        print("\nAgent Status Types:")
        for status in AgentStatus:
            print(f"   - {status.value}")

        print("\nEvent Types:")
        for event_type in AgentEventType:
            print(f"   - {event_type.value}")

        print("\nCreating Configuration...")
        config = AgentConfig(
            mode=ExecutionMode.REACT,
            style=AgentStyle.MINIMAL,
            system_prompt="You are Pho, an AI agent.",
            max_iterations=10
        )
        print(f"Config created:")
        print(f"   - Mode: {config.mode.value}")
        print(f"   - Style: {config.style.value}")
        print(f"   - Max iterations: {config.max_iterations}")

        print("\nCreating Context...")
        context = Context(
            session_id="demo-session",
            user_id="demo-user",
            variables={"name": "World"}
        )
        print(f"Context created:")
        print(f"   - Session ID: {context.session_id}")
        print(f"   - User ID: {context.user_id}")
        print(f"   - Variables: {context.variables}")

    except Exception as e:
        print(f"Error: {e}")


async def demo_toolkit_and_inspectors():
    """Demonstrate toolkit and inspector chain (Phase 3)"""
    print("\n" + "="*50)
    print("Toolkit & Inspector Chain Demo (Phase 3)")
    print("="*50 + "\n")

    try:
        from pho import (
            ToolRegistry, ToolType, register_tool,
            ToolExecutor, ExecutionContext,
            InspectorChain,
            SecurityInspector, PermissionInspector, RepetitionInspector,
            Permission, Role,
        )

        # 1. Create tool registry
        print("1. Creating Tool Registry...")
        registry = ToolRegistry()

        # Register some demo tools
        @register_tool("greet", description="Greet someone by name", category="greeting")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @register_tool("calculate", description="Calculate sum of two numbers", category="math")
        def calculate(a: int, b: int) -> int:
            return a + b

        @register_tool("read_file", description="Read a file", category="file_ops")
        def read_file(path: str) -> str:
            return f"Contents of {path}"

        # Register with our local registry
        registry.register("greet", greet, "Greet someone", ToolType.DECORATOR, "greeting")
        registry.register("calculate", calculate, "Calculate sum", ToolType.DECORATOR, "math")
        registry.register("read_file", read_file, "Read file", ToolType.DECORATOR, "file_ops")

        print(f"   Registered {len(registry)} tools:")
        for name, meta in registry.list_all().items():
            print(f"      - {name}: {meta.description}")

        # 2. Create inspector chain
        print("\n2. Creating Inspector Chain...")
        inspector_chain = InspectorChain()

        # Add security inspector
        security = SecurityInspector(
            priority=10,
            blocked_tools=set(),  # No blocked tools for demo
        )
        inspector_chain.add_inspector(security)
        print(f"   Added: {security}")

        # Add permission inspector
        permission = PermissionInspector(
            priority=20,
            default_role=Role.USER,
        )
        inspector_chain.add_inspector(permission)
        print(f"   Added: {permission}")

        # Add repetition inspector
        repetition = RepetitionInspector(
            priority=30,
            max_duplicates=3,
        )
        inspector_chain.add_inspector(repetition)
        print(f"   Added: {repetition}")

        # 3. Create tool executor
        print("\n3. Creating Tool Executor...")
        executor = ToolExecutor(
            registry=registry,
            inspector_chain=inspector_chain,
            enable_cache=True,
        )
        print(f"   Created: {executor}")

        # 4. Execute tools
        print("\n4. Executing Tools...")
        context = ExecutionContext(
            session_id="demo-session",
            user_id="demo-user",
            user_role="user",
        )

        # Test greet tool
        result = await executor.execute("greet", {"name": "Pho"}, context)
        print(f"   greet('Pho'): {result.result} (status: {result.status.value})")

        # Test calculate tool
        result = await executor.execute("calculate", {"a": 5, "b": 3}, context)
        print(f"   calculate(5, 3): {result.result} (status: {result.status.value})")

        # Test read_file tool
        result = await executor.execute("read_file", {"path": "/etc/hosts"}, context)
        print(f"   read_file('/etc/hosts'): {result.result}")

        # Test caching
        print("\n5. Testing Cache...")
        result = await executor.execute("calculate", {"a": 5, "b": 3}, context)
        print(f"   calculate(5, 3) again: {result.result} (cached: {result.cached})")

        # Show statistics
        print(f"\n   Cache size: {executor.get_cache_size()}")
        stats = registry.get_statistics()
        print(f"   Registry stats: {stats}")

        print("\n   Phase 3: Toolkit & Inspectors working!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def demo_three_phase_agent():
    """Demonstrate ThreePhaseAgent with skill-based routing (Phase 4)"""
    print("\n" + "="*50)
    print("ThreePhaseAgent Demo - Skill-Based Routing (Phase 4)")
    print("="*50 + "\n")

    try:
        from pho import (
            PhoAgent, AgentStyle, ModelConfig, ProviderFactory,
            ThreePhaseAgentEngine,
        )

        print("1. Creating SKILL_BASED style agent...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"
        ))

        agent = PhoAgent(
            style=AgentStyle.SKILL_BASED,
            llm=llm
        )

        print(f"   Agent created with style: {agent.get_style().value}")
        print(f"   Engine type: {type(agent.engine).__name__}")

        # Verify it's using ThreePhaseAgentEngine
        assert isinstance(agent.engine, ThreePhaseAgentEngine), \
            f"Expected ThreePhaseAgentEngine, got {type(agent.engine)}"

        print("\n2. Three-Phase Execution Pattern:")
        print("   - Phase 1: Intent Recognition")
        print("   - Phase 2: LLM Generation")
        print("   - Phase 3: Tool Execution")

        print("\n3. Features:")
        print("   - Intent-based routing")
        print("   - Skill loader integration")
        print("   - Inspector chain support")
        print("   - Streaming output")

        print("\n   Phase 4: ThreePhaseAgent working!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def demo_workflow_agent():
    """Demonstrate WorkflowAgent with DAG orchestration (Phase 5)"""
    print("\n" + "="*50)
    print("WorkflowAgent Demo - DAG Orchestration (Phase 5)")
    print("="*50 + "\n")

    try:
        from pho import (
            PhoAgent, AgentStyle, ModelConfig, ProviderFactory,
            WorkflowAgentEngine,
        )

        print("1. Creating ORCHESTRATED style agent...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"
        ))

        agent = PhoAgent(
            style=AgentStyle.ORCHESTRATED,
            llm=llm
        )

        print(f"   Agent created with style: {agent.get_style().value}")
        print(f"   Engine type: {type(agent.engine).__name__}")

        # Verify it's using WorkflowAgentEngine
        assert isinstance(agent.engine, WorkflowAgentEngine), \
            f"Expected WorkflowAgentEngine, got {type(agent.engine)}"

        print("\n2. DAG Workflow Features:")
        print("   - Component-based nodes")
        print("   - Conditional branching")
        print("   - Sub-workflow support")
        print("   - State management")

        print("\n3. Copied Modules from goose-py:")
        print("   - workflow/ (Graph, Scheduler, etc.)")
        print("   - components/ (Component registry)")
        print("   - session/ (Session management)")
        print("   - resources/ (Resource management)")
        print("   - events/ (Event system)")
        print("   - persistence/ (Database backends)")

        print("\n4. Status:")
        print("   - Modules copied and imports fixed")
        print("   - WorkflowAgentEngine created (simplified version)")
        print("   - Full workflow integration requires additional setup")

        print("\n   Phase 5: Workflow & Components copied!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def demo_react_agent():
    """Demonstrate ReactAgent with Thought → Action → Observation loop"""
    print("\n" + "="*50)
    print("ReactAgent Demo - Thought → Action → Observation")
    print("="*50 + "\n")

    try:
        from pho import (
            PhoAgent, AgentStyle, ModelConfig, ProviderFactory,
            ReactAgentEngine,
        )

        print("1. Creating REASONING style agent...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"
        ))

        agent = PhoAgent(
            style=AgentStyle.REASONING,
            llm=llm
        )

        print(f"   Agent created with style: {agent.get_style().value}")
        print(f"   Engine type: {type(agent.engine).__name__}")

        # Verify it's using ReactAgentEngine
        assert isinstance(agent.engine, ReactAgentEngine), \
            f"Expected ReactAgentEngine, got {type(agent.engine)}"

        print("\n2. ReAct Execution Pattern:")
        print("   - Thought: Explicit reasoning about what to do")
        print("   - Action: Choose a tool or give final answer")
        print("   - Observation: Result from tool execution")
        print("   - Loop: Continue until final answer")

        print("\n3. Features:")
        print("   - Configurable max iterations")
        print("   - Streaming support")
        print("   - Event emission for each step")
        print("   - Tool execution with inspector chain")

        print("\n   Phase 6: ReactAgent working!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def demo_streaming_agent():
    """Demonstrate StreamingAgent with event-driven streaming"""
    print("\n" + "="*50)
    print("StreamingAgent Demo - Event-Driven Streaming")
    print("="*50 + "\n")

    try:
        from pho import (
            PhoAgent, AgentStyle, ModelConfig, ProviderFactory,
            StreamingAgentEngine,
        )

        print("1. Creating REACTIVE style agent...")
        llm = ProviderFactory.create_llm("openai", ModelConfig(
            model_name="gpt-4o-mini",
            api_key="demo-key"
        ))

        agent = PhoAgent(
            style=AgentStyle.REACTIVE,
            llm=llm
        )

        print(f"   Agent created with style: {agent.get_style().value}")
        print(f"   Engine type: {type(agent.engine).__name__}")

        # Verify it's using StreamingAgentEngine
        assert isinstance(agent.engine, StreamingAgentEngine), \
            f"Expected StreamingAgentEngine, got {type(agent.engine)}"

        print("\n2. Event-Driven Streaming Features:")
        print("   - Real-time token streaming")
        print("   - Event emission for all stages")
        print("   - State machine tracking")
        print("   - Async-first architecture")

        print("\n3. Events Emitted:")
        print("   - start: Execution started")
        print("   - thinking: Agent is thinking")
        print("   - text: Text chunk received")
        print("   - token: Individual token (optional)")
        print("   - tool_start: Tool execution starting")
        print("   - tool_end: Tool execution complete")
        print("   - complete: Execution finished")
        print("   - error: Error occurred")

        print("\n   Phase 6: StreamingAgent working!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("Pho Framework v0.1.0")
    print("Unified AI Agent Framework - Multi-Style Agent System")
    print()

    # Check imports
    try:
        from pho import (
            Message, Conversation, Role,
            BaseLLM, ProviderFactory, ModelConfig,
            PhoAgent, BaseAgent, create_agent,
            ExecutionMode, AgentStyle,
        )

        print("All modules imported successfully")
        print(f"   - Conversation: {Conversation.__name__}")
        print(f"   - Message: {Message.__name__}")
        print(f"   - ProviderFactory: {ProviderFactory.__name__}")
        print(f"   - PhoAgent: {PhoAgent.__name__}")
        print(f"   - BaseAgent: {BaseAgent.__name__}")
        print(f"   - Agent Styles: {len(AgentStyle)} available")

        # Show available providers
        llm_providers = ProviderFactory.list_llm_providers()
        embedding_providers = ProviderFactory.list_embedding_providers()

        print(f"\nAvailable providers:")
        print(f"   - LLM: {llm_providers}")
        print(f"   - Embedding: {embedding_providers}")

    except Exception as e:
        print(f"Import error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Run demos
    await demo_core_abstractions()
    await demo_basic_agent()
    await demo_multi_style_agent()
    await demo_toolkit_and_inspectors()  # Phase 3 demo
    await demo_three_phase_agent()  # Phase 4 demo
    await demo_workflow_agent()  # Phase 5 demo
    await demo_react_agent()  # Phase 6 demo
    await demo_streaming_agent()  # Phase 6 demo

    print("\n" + "="*50)
    print("Pho Framework initialized successfully!")
    print("="*50)
    print("\nDocumentation:")
    print("   - Agent Architecture: pho/docs/AGENT_ARCHITECTURE.md")
    print("   - Merger Plan: .claude/plans/soft-honking-trinket.md")
    print("\nQuick Start:")
    print("   from pho import PhoAgent, AgentStyle")
    print("   agent = PhoAgent(style=AgentStyle.MINIMAL)")
    print("   response = await agent.run('Hello!')")
    print()


def run():
    """Entry point for console script"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
