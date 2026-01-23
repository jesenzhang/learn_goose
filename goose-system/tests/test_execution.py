"""
Tests for execution module
"""

import pytest
import asyncio
from datetime import datetime
from goose.execution import (
    SessionExecutionMode,
    AgentInfo,
    LRUCache,
    AgentManager,
    ExecutionContext,
    get_agent_manager,
    get_or_create_agent,
    create_execution_context,
)


class TestSessionExecutionMode:
    """Test SessionExecutionMode enum"""

    def test_chat_mode(self):
        mode = SessionExecutionMode.chat()
        assert mode == SessionExecutionMode.INTERACTIVE

    def test_scheduled_mode(self):
        mode = SessionExecutionMode.scheduled()
        assert mode == SessionExecutionMode.BACKGROUND

    def test_task_mode(self):
        mode = SessionExecutionMode.task(parent="parent-session")
        assert mode == SessionExecutionMode.SUBTASK

    def test_mode_values(self):
        assert SessionExecutionMode.INTERACTIVE.value == "interactive"
        assert SessionExecutionMode.BACKGROUND.value == "background"
        assert SessionExecutionMode.SUBTASK.value == "subtask"


class TestAgentInfo:
    """Test AgentInfo dataclass"""

    def test_agent_info_creation(self):
        agent = object()
        info = AgentInfo(
            agent=agent,
            session_id="test-session",
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert info.agent is agent
        assert info.session_id == "test-session"
        assert info.execution_mode == SessionExecutionMode.INTERACTIVE
        assert info.parent_session is None

    def test_agent_info_with_parent(self):
        info = AgentInfo(
            agent=object(),
            session_id="child-session",
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            execution_mode=SessionExecutionMode.SUBTASK,
            parent_session="parent-session",
        )
        assert info.parent_session == "parent-session"

    def test_agent_info_to_dict(self):
        now = datetime.utcnow()
        info = AgentInfo(
            agent=object(),
            session_id="test-session",
            created_at=now,
            last_active=now,
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        result = info.to_dict()
        assert result["session_id"] == "test-session"
        assert result["execution_mode"] == "interactive"
        assert "created_at" in result
        assert "last_active" in result


class TestLRUCache:
    """Test LRUCache implementation"""

    def test_lru_cache_basic_operations(self):
        cache = LRUCache(capacity=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.len() == 3

    def test_lru_cache_eviction(self):
        cache = LRUCache(capacity=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")
        cache.put("key4", "value4")

        assert cache.get("key1") is None
        assert cache.get("key4") == "value4"
        assert cache.len() == 3

    def test_lru_cache_move_to_end(self):
        cache = LRUCache(capacity=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")
        cache.get("key1")
        cache.put("key4", "value4")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None

    def test_lru_cache_contains(self):
        cache = LRUCache(capacity=2)
        cache.put("key1", "value1")
        assert cache.contains("key1")
        assert not cache.contains("key2")

    def test_lru_cache_pop(self):
        cache = LRUCache(capacity=2)
        cache.put("key1", "value1")
        value = cache.pop("key1")
        assert value == "value1"
        assert cache.get("key1") is None

    def test_lru_cache_keys(self):
        cache = LRUCache(capacity=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        keys = cache.keys()
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys

    def test_lru_cache_clear(self):
        cache = LRUCache(capacity=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.clear()
        assert cache.len() == 0


class TestAgentManager:
    """Test AgentManager"""

    @pytest.fixture
    def manager(self):
        """Create a fresh AgentManager for each test"""
        AgentManager.set_instance(None)
        manager = AgentManager(max_sessions=5)
        yield manager
        AgentManager.set_instance(None)

    def test_agent_manager_singleton(self, manager):
        instance1 = AgentManager.get_instance()
        instance2 = AgentManager.get_instance()
        assert instance1 is instance2

    def test_agent_manager_initial_state(self, manager):
        assert manager.session_count() == 0
        assert manager.max_sessions == 5
        assert manager.session_manager is None
        assert manager.scheduler is None

    def test_has_session_empty(self, manager):
        assert not manager.has_session("test-session")

    def test_get_session_ids_empty(self, manager):
        assert manager.get_session_ids() == []

    def test_get_agent_info_not_found(self, manager):
        info = manager.get_agent_info("test-session")
        assert info is None

    def test_get_all_agent_info_empty(self, manager):
        info = manager.get_all_agent_info()
        assert info == []

    def test_get_active_sessions_empty(self, manager):
        active = manager.get_active_sessions()
        assert active == []

    @pytest.mark.asyncio
    async def test_get_or_create_agent_creates_new(self, manager):
        agent = await manager.get_or_create_agent(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert agent is not None
        assert manager.has_session("test-session")
        assert manager.session_count() == 1

    @pytest.mark.asyncio
    async def test_get_or_create_agent_returns_cached(self, manager):
        agent1 = await manager.get_or_create_agent(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        agent2 = await manager.get_or_create_agent(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert agent1 is agent2
        assert manager.session_count() == 1

    @pytest.mark.asyncio
    async def test_get_or_create_agent_different_sessions(self, manager):
        agent1 = await manager.get_or_create_agent(
            session_id="session-1",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        agent2 = await manager.get_or_create_agent(
            session_id="session-2",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert agent1 is not agent2
        assert manager.session_count() == 2

    @pytest.mark.asyncio
    async def test_get_or_create_agent_with_parent(self, manager):
        agent = await manager.get_or_create_agent(
            session_id="child-session",
            execution_mode=SessionExecutionMode.SUBTASK,
            parent_session="parent-session",
        )
        assert agent is not None
        info = manager.get_agent_info("child-session")
        assert info is not None
        assert info.parent_session == "parent-session"

    @pytest.mark.asyncio
    async def test_remove_session(self, manager):
        await manager.get_or_create_agent(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert manager.has_session("test-session")

        result = await manager.remove_session("test-session")
        assert result
        assert not manager.has_session("test-session")
        assert manager.session_count() == 0

    @pytest.mark.asyncio
    async def test_remove_session_not_exists(self, manager):
        result = await manager.remove_session("non-existent")
        assert not result

    @pytest.mark.asyncio
    async def test_clear_all_sessions(self, manager):
        await manager.get_or_create_agent(
            session_id="session-1",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        await manager.get_or_create_agent(
            session_id="session-2",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert manager.session_count() == 2

        manager.clear_all_sessions()
        assert manager.session_count() == 0

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, manager):
        for i in range(10):
            agent = await manager.get_or_create_agent(
                session_id=f"session-{i}",
                execution_mode=SessionExecutionMode.INTERACTIVE,
            )
        assert manager.session_count() == 5

    def test_set_default_provider(self, manager):
        provider = object()
        manager.set_default_provider(provider)
        assert manager._default_provider is provider

    def test_get_agent_info(self, manager):
        info = AgentInfo(
            agent=object(),
            session_id="test-session",
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        manager._agent_info["test-session"] = info
        result = manager.get_agent_info("test-session")
        assert result is info


class TestExecutionContext:
    """Test ExecutionContext"""

    @pytest.fixture
    def manager(self):
        AgentManager.set_instance(None)
        return AgentManager(max_sessions=5)

    def test_execution_context_creation(self):
        ctx = create_execution_context(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert ctx.session_id == "test-session"
        assert ctx.execution_mode == SessionExecutionMode.INTERACTIVE
        assert ctx.parent_session is None

    def test_execution_context_with_parent(self):
        ctx = create_execution_context(
            session_id="child-session",
            execution_mode=SessionExecutionMode.SUBTASK,
            parent_session="parent-session",
        )
        assert ctx.parent_session == "parent-session"


class TestShortcutFunctions:
    """Test shortcut functions"""

    @pytest.fixture
    def manager(self):
        AgentManager.set_instance(None)
        return AgentManager(max_sessions=5)

    def test_get_agent_manager(self, manager):
        result = get_agent_manager()
        assert result is not None
        AgentManager.set_instance(None)

    @pytest.mark.asyncio
    async def test_get_or_create_agent_shortcut(self, manager):
        agent = await get_or_create_agent(
            session_id="test-session",
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
        assert agent is not None
        AgentManager.set_instance(None)
