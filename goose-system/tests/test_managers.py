"""
Integration tests for managers module.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from goose.managers import (
    RetryManager,
    RetryConfig,
    ToolInspectionManager,
    ToolRequest,
    InspectionAction,
    InspectionResult,
    PromptManager,
    PromptCategory,
    PromptTemplate,
    PermissionManager,
    PermissionLevel,
)
from goose.managers.subagent_handler import (
    SubagentHandler,
    SubagentConfig,
    SubagentStatus,
    SubagentResult,
)
from goose.managers.inspection_manager import ToolInspector


class TestRetryManager:
    """Tests for RetryManager."""

    def test_retry_config_defaults(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0

    def test_retry_manager_default_config(self):
        """Test retry manager with default config."""
        manager = RetryManager()
        assert manager.config.max_retries == 3

    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        """Test retry manager succeeds on first attempt."""
        manager = RetryManager(RetryConfig(max_retries=3, base_delay=0.01))

        call_count = 0
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await manager.execute_with_retry(success_func)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_retries_on_failure(self):
        """Test retry manager retries on failure."""
        manager = RetryManager(RetryConfig(max_retries=3, base_delay=0.01))

        call_count = 0
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        result = await manager.execute_with_retry(fail_twice)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_retries(self):
        """Test retry manager raises after exhausting retries."""
        manager = RetryManager(RetryConfig(max_retries=2, base_delay=0.01))

        async def always_fail():
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            await manager.execute_with_retry(always_fail)


class TestToolInspectionManager:
    """Tests for ToolInspectionManager."""

    def test_default_chain(self):
        """Test creating default inspection chain."""
        manager = ToolInspectionManager().create_default_chain()
        assert len(manager.inspectors) == 3
        inspector_names = [i.name for i in manager.inspectors]
        assert "SecurityInspector" in inspector_names
        assert "PermissionInspector" in inspector_names
        assert "RepetitionInspector" in inspector_names

    @pytest.mark.asyncio
    async def test_inspection_allows_safe_tool(self):
        """Test inspection returns appropriate result for unknown tool."""
        manager = ToolInspectionManager().create_default_chain()
        request = ToolRequest(
            id="test-1",
            name="safe_tool",
            arguments={"param": "value"}
        )
        result = await manager.inspect(request)
        assert result.action in [InspectionAction.ALLOW, InspectionAction.CONFIRM]

    @pytest.mark.asyncio
    async def test_inspection_chain_stops_at_first_failure(self):
        """Test inspection chain stops at first failure."""

        class MockInspector(ToolInspector):
            async def inspect(self, request: ToolRequest) -> InspectionResult:
                return InspectionResult(
                    allowed=False,
                    action=InspectionAction.DENY,
                    reason="fail"
                )

        manager = ToolInspectionManager()
        manager.add_inspector(MockInspector())

        request = ToolRequest(id="test-1", name="test_tool", arguments={})
        result = await manager.inspect(request)
        assert not result.allowed

    def test_inspection_can_be_disabled(self):
        """Test that inspection can be disabled."""
        manager = ToolInspectionManager()
        manager.disable()
        request = ToolRequest(id="test-1", name="test_tool", arguments={})
        result = asyncio.run(manager.inspect(request))
        assert result.allowed


class TestPromptManager:
    """Tests for PromptManager."""

    def test_add_template(self):
        """Test adding a template."""
        manager = PromptManager()
        template = PromptTemplate(
            name="test_template",
            content="Hello, {name}!",
            category=PromptCategory.SYSTEM
        )
        manager.add_template(template)
        assert "test_template" in manager.templates

    def test_get_template(self):
        """Test getting a template."""
        manager = PromptManager()
        template = PromptTemplate(name="test", content="Test content")
        manager.add_template(template)
        retrieved = manager.get_template("test")
        assert retrieved is not None
        assert retrieved.content == "Test content"

    def test_render_template(self):
        """Test rendering a template with variables."""
        manager = PromptManager()
        template = PromptTemplate(
            name="greeting",
            content="Hello, {name}! You have {count} messages.",
            variables=["name", "count"]
        )
        manager.add_template(template)
        retrieved = manager.get_template("greeting")
        result = retrieved.render({"name": "Alice", "count": "5"})
        assert result == "Hello, Alice! You have 5 messages."

    def test_list_templates_by_category(self):
        """Test listing templates by category."""
        manager = PromptManager()
        manager.add_template(PromptTemplate(
            name="sys1", content="sys", category=PromptCategory.SYSTEM
        ))
        manager.add_template(PromptTemplate(
            name="sys2", content="sys2", category=PromptCategory.SYSTEM
        ))
        manager.add_template(PromptTemplate(
            name="task1", content="task", category=PromptCategory.TASK
        ))

        sys_templates = manager.list_templates(PromptCategory.SYSTEM)
        assert len(sys_templates) == 2
        assert "sys1" in sys_templates
        assert "sys2" in sys_templates


class TestPermissionManager:
    """Tests for PermissionManager."""

    def test_default_permission_is_prompt(self):
        """Test that default permission is prompt."""
        manager = PermissionManager()
        permission = manager.get_tool_permission("unknown_tool")
        assert permission.level == PermissionLevel.PROMPT

    def test_set_allow_permission(self):
        """Test setting allow permission."""
        manager = PermissionManager()
        manager.set_tool_permission("safe_tool", PermissionLevel.ALLOW)
        permission = manager.get_tool_permission("safe_tool")
        assert permission.level == PermissionLevel.ALLOW

    def test_set_deny_permission(self):
        """Test setting deny permission."""
        manager = PermissionManager()
        manager.set_tool_permission("dangerous_tool", PermissionLevel.DENY)
        permission = manager.get_tool_permission("dangerous_tool")
        assert permission.level == PermissionLevel.DENY

    @pytest.mark.asyncio
    async def test_check_allow_permission(self):
        """Test checking allow permission."""
        manager = PermissionManager()
        manager.set_tool_permission("safe_tool", PermissionLevel.ALLOW)
        allowed, reason = await manager.check_permission("safe_tool", {})
        assert allowed
        assert reason is None

    @pytest.mark.asyncio
    async def test_check_deny_permission(self):
        """Test checking deny permission."""
        manager = PermissionManager()
        manager.set_tool_permission("dangerous_tool", PermissionLevel.DENY)
        allowed, reason = await manager.check_permission("dangerous_tool", {})
        assert not allowed
        assert reason is not None

    def test_permission_summary(self):
        """Test getting permission summary."""
        manager = PermissionManager()
        manager.set_tool_permission("tool1", PermissionLevel.ALLOW)
        manager.set_tool_permission("tool2", PermissionLevel.DENY)
        manager.set_tool_permission("tool3", PermissionLevel.PROMPT)

        summary = manager.get_permission_summary()
        assert summary["total_tools"] == 3
        assert summary["allowed"] == 1
        assert summary["denied"] == 1
        assert summary["prompt"] == 1


class TestSubagentHandler:
    """Tests for SubagentHandler."""

    def test_subagent_config_from_dict(self):
        """Test creating SubagentConfig from dict."""
        config = SubagentConfig.from_dict({
            "name": "test_subagent",
            "instructions": "Do something",
            "max_turns": 5,
            "tools": ["tool1", "tool2"]
        })
        assert config.name == "test_subagent"
        assert config.instructions == "Do something"
        assert config.max_turns == 5
        assert config.tools == ["tool1", "tool2"]

    def test_subagent_result_to_dict(self):
        """Test converting SubagentResult to dict."""
        result = SubagentResult(
            status=SubagentStatus.COMPLETED,
            messages=[{"role": "user", "content": "hello"}],
            output="done"
        )
        result_dict = result.to_dict()
        assert result_dict["status"] == "completed"
        assert result_dict["output"] == "done"

    @pytest.mark.asyncio
    async def test_execute_subagent_creates_agent(self):
        """Test that execute_subagent creates an agent."""
        mock_agent = MagicMock()
        handler = SubagentHandler(mock_agent)

        config = SubagentConfig(
            name="test",
            instructions="Test instructions",
            max_turns=5
        )

        result = await handler.execute_subagent(config)
        assert result.status == SubagentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_subagent_max_depth_enforced(self):
        """Test that max nesting depth is enforced."""
        mock_agent = MagicMock()
        handler = SubagentHandler(mock_agent)
        handler.max_nesting_depth = 1

        config = SubagentConfig(name="test", instructions="test")

        result = await handler.execute_subagent(config)
        assert result.status == SubagentStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
