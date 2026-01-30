"""
Jarvis Demo - Showcasing the Event-sourced Agent Runtime.

This demo shows:
1. Event sourcing and replay
2. Pure agent reducers
3. Effect-based execution
4. Async/Concurrent execution
"""

import asyncio
import logging
import sys

# Add jarvis_core to path
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class EventPrinter:
    """Print events as they happen."""

    def __init__(self, session_id: str):
        self.session_id = session_id

    def __call__(self, event: Event):
        if event.session_id != self.session_id:
            return

        print(f"\n📦 Event: {event.type}")
        print(f"   Session: {event.session_id}")
        print(f"   Run: {event.run_id}")
        print(f"   Seq: {event.seq_id}")

        if event.payload:
            print(f"   Payload: {event.payload}")


async def simple_demo():
    """Simple demo with mock executor."""
    print("\n" + "=" * 60)
    print("SIMPLE DEMO - Mock Agent Runtime")
    print("=" * 60 + "\n")

    # Create agent
    agent = SimpleChatAgent(
        system_prompt="You are a helpful assistant. Be concise.",
        max_history=5,
    )

    # Create runtime
    runtime = create_runtime(
        agent=agent,
        config={
            "executor": "mock",
            "event_store": "memory",
        },
    )

    # Register event printer
    session_id = "demo_session_1"
    printer = EventPrinter(session_id)
    runtime.on_event(printer)

    # Create user input event
    input_event = Event.new(
        session_id=session_id,
        agent_id=agent.id,
        run_id="demo_run",
        type="user_input",
        payload={"message": "Hello Jarvis! What can you do?"},
    )

    # Run the task
    print("🚀 Starting task...")
    task_handle = await runtime.run(
        session_id=session_id,
        input_event=input_event,
    )

    # Wait for completion
    while task_handle.is_running:
        await asyncio.sleep(0.1)

    print(f"\n✅ Task completed in {task_handle.duration:.2f}s")

    # Show session state
    sessions = await runtime.list_sessions()
    print(f"\n📊 Sessions: {len(sessions)}")
    for s in sessions:
        print(f"   - {s['session_id']}: {s['status']}")


async def tool_using_demo():
    """Demo with tool-using agent."""
    print("\n" + "=" * 60)
    print("TOOL-USING DEMO - Agent with Tool Support")
    print("=" * 60 + "\n")

    # Create agent with tools
    agent = ToolUsingAgent(
        system_prompt="You are a helpful assistant with access to tools.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Perform calculations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Math expression",
                            }
                        },
                        "required": ["expression"],
                    },
                },
            },
        ],
    )

    # Create runtime with mock executor
    runtime = create_runtime(
        agent=agent,
        config={
            "executor": "mock",
            "event_store": "memory",
        },
    )

    # Register event printer
    session_id = "demo_session_2"
    printer = EventPrinter(session_id)
    runtime.on_event(printer)

    # Create events that simulate a conversation
    events = [
        Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id="demo_run",
            type="user_input",
            payload={"message": "Calculate 2 + 2"},
        ),
        Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id="demo_run",
            type="user_input",
            payload={"message": "Now search for information about AI"},
        ),
    ]

    # Run events
    for i, event in enumerate(events):
        print(f"\n📨 Input {i + 1}: {event.payload.get('message')}")

        task_handle = await runtime.run(
            session_id=session_id,
            input_event=event,
        )

        while task_handle.is_running:
            await asyncio.sleep(0.1)

        print(f"✅ Completed in {task_handle.duration:.2f}s")

    print("\n✅ All inputs processed!")


async def replay_demo():
    """Demo event replay functionality."""
    print("\n" + "=" * 60)
    print("REPLAY DEMO - Event Sourcing and Replay")
    print("=" * 60 + "\n")

    # Create agent
    agent = SimpleChatAgent(
        system_prompt="You are a helpful assistant.",
    )

    # Create runtime with SQLite for persistence
    runtime = create_runtime(
        agent=agent,
        config={
            "executor": "mock",
            "event_store": "sqlite",
            "event_db_path": "demo_replay_events.db.db",
            "state_db_path": "demo_replay_state.db",
        },
    )

    session_id = "replay_session"
    run_id = "replay_run"

    # Create original events
    original_events = [
        Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id=run_id,
            type="user_input",
            payload={"message": "What is the capital of France?"},
        ),
        Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id=run_id,
            type="user_input",
            payload={"message": "And what about Germany?"},
        ),
    ]

    # Run original events
    print("📝 Running original events...")
    for i, event in enumerate(original_events):
        printer = EventPrinter(session_id)
        runtime.on_event(printer)

        task_handle = await runtime.run(
            session_id=session_id,
            input_event=event,
        )

        while task_handle.is_running:
            await asyncio.sleep(0.1)

    print(f"\n✅ Completed {len(original_events)} original events")

    # Now replay from the store
    print("\n🔄 Replaying events from store...")

    # Register replay-specific printer
    replay_printer = EventPrinter(f"{session_id}_replay")
    runtime.on_event(replay_printer)

    # Replay all events
    replayed_events = await runtime.replay(
        session_id=session_id,
        run_id=run_id,
        from_seq_id=0,
        mode="dry_run",  # Don't execute effects, just replay
    )

    print(f"\n✅ Replayed {len(replayed_events)} events")

    # Show events were persisted
    print("\n📊 Events in store:")
    events_in_store = []
    async for event in runtime._event_store.load(session_id, run_id):
        events_in_store.append(event)

    for event in events_in_store:
        print(f"   Seq {event.seq_id}: {event.type}")

    # Cleanup
    await runtime.close()


async def full_assistant_demo():
    """Demo with the full-featured assistant agent."""
    print("\n" + "=" * 60)
    print("FULL ASSISTANT DEMO - Complete Feature Set")
    print("=" * 60 + "\n")

    from examples.full_assistant_agent import FullAssistantAgent

    # Create full assistant
    agent = FullAssistantAgent(
        system_prompt="You are Jarvis, an intelligent assistant.",
        enable_deep_thinking=True,
        max_history=20,
    )

    # Create runtime
    runtime = create_runtime(
        agent=agent,
        config={
            "executor": "mock",  # Use mock for demo
            "event_store": "memory",
        },
    )

    # Register event printer
    session_id = "full_demo_session"
    printer = EventPrinter(session_id)
    runtime.on_event(printer)

    # Simulate a complex interaction
    interactions = [
        "Help me plan a trip to Tokyo",
        "Search for flights from Shanghai to Tokyo next month",
        "Calculate the total cost with hotel and food",
        "Exit to global context",
    ]

    for interaction in interactions:
        print(f"\n💬 User: {interaction}")

        input_event = Event.new(
            session_id=session_id,
            agent_id=agent.id,
            run_id="full_demo_run",
            type="user_input",
            payload={
                "message": interaction,
                "deep_thinking": True,
            },
        )

        task = await runtime.run(session_id, input_event)
        while task.is_running:
            await asyncio.sleep(0.1)

    print("\n✅ Full assistant demo completed!")

    # Show session state
    state = await runtime._state_store.load_state(session_id)
    if state:
        print(f"\n📊 Session State:")
        print(f"   Status: {state.status}")
        print(f"   Active Skill: {state.active_skill}")
        print(f"   Messages in history: {len(state.history)}")


async def main():
    """Main entry point."""
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                      ║
║  JARVIS - Event-Sourced Agent Runtime Demo         ║
║                                                      ║
║  A production-grade Agent Runtime with:            ║
║  - Event Sourcing (replayability)               ║
║  - Pure Agent Reducers (testability)           ║
║  - Effect-based Execution (side effects)       ║
║  - Async/Concurrent support                       ║
║                                                      ║
╚══════════════════════════════════════════════════════════╝
    """)

    # Run demos
    await simple_demo()
    await asyncio.sleep(1)

    await tool_using_demo()
    await asyncio.sleep(1)

    await replay_demo()
    await asyncio.sleep(1)

    await full_assistant_demo()

    print("\n" + "=" * 60)
    print("All demos completed! ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
