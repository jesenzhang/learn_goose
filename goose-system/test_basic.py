"""
Basic test for goose-system framework
"""
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

def test_imports():
    """Test basic imports"""
    print("Testing imports...")

    try:
        from goose.agent import Agent, AgentConfig
        print("  - goose.agent: OK")
    except Exception as e:
        print(f"  - goose.agent: FAILED - {e}")

    try:
        from goose.skills import Skill, SkillRegistry
        print("  - goose.skills: OK")
    except Exception as e:
        print(f"  - goose.skills: FAILED - {e}")

    try:
        from goose.tools import Tool, FunctionTool
        print("  - goose.tools: OK")
    except Exception as e:
        print(f"  - goose.tools: FAILED - {e}")

    try:
        from goose.conversation import Conversation, Message
        print("  - goose.conversation: OK")
    except Exception as e:
        print(f"  - goose.conversation: FAILED - {e}")

    try:
        from goose.providers import create_provider
        print("  - goose.providers: OK")
    except Exception as e:
        print(f"  - goose.providers: FAILED - {e}")

def test_basic_classes():
    """Test basic class instantiation"""
    print("\nTesting basic classes...")

    try:
        config = AgentConfig()
        print(f"  - AgentConfig: OK (session_id={config.session_id[:8]}...)")
    except Exception as e:
        print(f"  - AgentConfig: FAILED - {e}")

    try:
        from goose.conversation import Message
        msg = Message.user("Hello")
        print(f"  - Message.user: OK (text='{msg.text}')")
    except Exception as e:
        print(f"  - Message.user: FAILED - {e}")

    try:
        conv = Conversation()
        conv.add_user_message("Test", [])
        print(f"  - Conversation: OK (messages={len(conv)})")
    except Exception as e:
        print(f"  - Conversation: FAILED - {e}")

    try:
        from goose.skills import SkillMetadata
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill",
            path="/test/path"
        )
        print(f"  - SkillMetadata: OK (name='{metadata.name}')")
    except Exception as e:
        print(f"  - SkillMetadata: FAILED - {e}")

def test_tools():
    """Test tool creation"""
    print("\nTesting tools...")

    try:
        from goose.tools import FunctionTool

        def hello_fn(name: str) -> str:
            return f"Hello, {name}!"

        tool = FunctionTool(
            name="hello",
            description="Say hello to someone",
            parameters={"name": {"type": "string", "description": "Name to greet"}},
            function=hello_fn
        )
        print(f"  - FunctionTool: OK (name='{tool.name}')")
    except Exception as e:
        print(f"  - FunctionTool: FAILED - {e}")

def test_skills():
    """Test skill loading"""
    print("\nTesting skills...")

    try:
        from goose.skills.loader import SkillLoader
        loader = SkillLoader()
        print(f"  - SkillLoader: OK")
    except Exception as e:
        print(f"  - SkillLoader: FAILED - {e}")

    try:
        from goose.skills.registry import SkillRegistry
        registry = SkillRegistry()
        print(f"  - SkillRegistry: OK (count={registry.count})")
    except Exception as e:
        print(f"  - SkillRegistry: FAILED - {e}")

def main():
    print("=" * 50)
    print("Goose-System Basic Test")
    print("=" * 50)

    test_imports()
    test_basic_classes()
    test_tools()
    test_skills()

    print("\n" + "=" * 50)
    print("Test completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
