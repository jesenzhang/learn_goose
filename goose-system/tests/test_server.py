"""
Tests for server module
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from goose.server.state import AppState, ServerConfig, create_app_state
from goose.server.routes.agent import (
    StartAgentRequest,
    StopAgentRequest,
    ToolInfo,
)
from goose.server.routes.session import (
    SessionListResponse,
    UpdateSessionNameRequest,
)
from goose.server.routes.recipe import (
    RecipeListResponse,
    ValidateRecipeResponse,
)
from goose.server.routes.config import (
    ConfigResponse,
    UpdateConfigRequest,
)
from goose.server.routes.status import HealthResponse


class TestServerConfig:
    """Test ServerConfig dataclass"""

    def test_default_config(self):
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.debug is False
        assert config.secret_key == ""

    def test_custom_config(self):
        config = ServerConfig(
            host="0.0.0.0",
            port=3000,
            debug=True,
            secret_key="test-key"
        )
        assert config.host == "0.0.0.0"
        assert config.port == 3000
        assert config.debug is True
        assert config.secret_key == "test-key"


class TestAppState:
    """Test AppState class"""

    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock AgentManager"""
        manager = MagicMock()
        manager.session_count.return_value = 0
        return manager

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock SessionManager"""
        manager = MagicMock()
        return manager

    def test_get_session_counter(self):
        config = ServerConfig()
        state = AppState(
            agent_manager=MagicMock(),
            session_manager=MagicMock(),
            server_config=config,
        )
        counter = state.get_session_counter()
        assert isinstance(counter, int)
        assert counter > 0


class TestAgentRequestModels:
    """Test Pydantic request models for agent routes"""

    def test_start_agent_request(self):
        request = StartAgentRequest(
            working_dir="/tmp",
            recipe_id="test-recipe"
        )
        assert request.working_dir == "/tmp"
        assert request.recipe_id == "test-recipe"
        assert request.recipe is None

    def test_start_agent_request_with_recipe(self):
        from goose.recipe import Recipe
        recipe = Recipe(title="Test", description="Test recipe")
        request = StartAgentRequest(
            working_dir="/tmp",
            recipe=recipe
        )
        assert request.recipe is not None
        assert request.recipe.title == "Test"

    def test_stop_agent_request(self):
        request = StopAgentRequest(session_id="test-session")
        assert request.session_id == "test-session"

    def test_tool_info(self):
        tool = ToolInfo(
            name="read_file",
            description="Read a file",
            parameters=["path"]
        )
        assert tool.name == "read_file"
        assert "path" in tool.parameters


class TestSessionRequestModels:
    """Test Pydantic request models for session routes"""

    def test_session_list_response(self):
        response = SessionListResponse(sessions=[])
        assert response.sessions == []

    def test_update_session_name_request(self):
        request = UpdateSessionNameRequest(name="New Session Name")
        assert request.name == "New Session Name"

    def test_update_session_name_max_length(self):
        from pydantic import ValidationError
        long_name = "a" * 201
        with pytest.raises(ValidationError):
            UpdateSessionNameRequest(name=long_name)


class TestRecipeRequestModels:
    """Test Pydantic request models for recipe routes"""

    def test_recipe_list_response(self):
        response = RecipeListResponse(recipes=[])
        assert response.recipes == []

    def test_recipe_list_with_items(self):
        recipes = [
            {"id": "recipe1", "title": "Recipe 1"},
            {"id": "recipe2", "title": "Recipe 2"},
        ]
        response = RecipeListResponse(recipes=recipes)
        assert len(response.recipes) == 2

    def test_validate_recipe_response_valid(self):
        response = ValidateRecipeResponse(valid=True, errors=[])
        assert response.valid is True
        assert response.errors == []

    def test_validate_recipe_response_invalid(self):
        response = ValidateRecipeResponse(
            valid=False,
            errors=["Title is required", "Description is required"]
        )
        assert response.valid is False
        assert len(response.errors) == 2


class TestConfigRequestModels:
    """Test Pydantic request models for config routes"""

    def test_config_response(self):
        response = ConfigResponse(config={"mode": "auto"})
        assert response.config["mode"] == "auto"

    def test_update_config_request(self):
        request = UpdateConfigRequest(
            mode="approve",
            goose_model="gpt-4",
            temperature=0.5
        )
        assert request.mode == "approve"
        assert request.goose_model == "gpt-4"
        assert request.temperature == 0.5

    def test_update_config_request_partial(self):
        request = UpdateConfigRequest(mode="chat")
        assert request.mode == "chat"
        assert request.goose_model is None
        assert request.temperature is None


class TestStatusModels:
    """Test Pydantic request models for status routes"""

    def test_health_response(self):
        response = HealthResponse(status="healthy", timestamp="2024-01-01T00:00:00")
        assert response.status == "healthy"
        assert response.timestamp == "2024-01-01T00:00:00"


class TestServerRouter:
    """Test ServerRouter functionality"""

    def test_create_server_router(self):
        from goose.server.routes.router import create_server_router
        router = create_server_router()
        assert router is not None


class TestServerImports:
    """Test server module imports"""

    def test_import_server_state(self):
        from goose.server.state import AppState, ServerConfig, create_app_state
        assert AppState is not None
        assert ServerConfig is not None
        assert create_app_state is not None

    def test_import_server_routes(self):
        from goose.server.routes import (
            agent,
            session,
            recipe,
            config,
            status,
        )
        assert agent is not None
        assert session is not None
        assert recipe is not None
        assert config is not None
        assert status is not None

    def test_import_server_main(self):
        from goose.server.main import create_app, run_server
        assert create_app is not None
        assert run_server is not None

    def test_import_from_goose(self):
        from goose import (
            create_app,
            run_server,
            AppState,
            ServerConfig,
        )
        assert create_app is not None
        assert run_server is not None
        assert AppState is not None
        assert ServerConfig is not None


@pytest.mark.asyncio
class TestServerIntegration:
    """Integration tests for the server with actual HTTP requests"""

    @pytest.fixture
    async def server_with_x_secret_key(self):
        """Create a test server with X-Secret-Key authentication"""
        import sys
        sys.path.insert(0, 'F:/Workspace/learn_goose/goose-system/src')
        sys.path = [p for p in sys.path if 'goose-py' not in p or 'goose-system' in p]

        from goose.server.main import create_app
        import uvicorn
        import asyncio

        app = create_app(secret_key='test_secret_key', token=None)
        config = uvicorn.Config(app, host='127.0.0.1', port=18080, log_level='error')
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        await asyncio.sleep(1)
        
        yield app
        
        server.should_exit = True
        await task

    @pytest.fixture
    async def server_with_bearer_token(self):
        """Create a test server with Bearer token authentication"""
        import sys
        sys.path.insert(0, 'F:/Workspace/learn_goose/goose-system/src')
        sys.path = [p for p in sys.path if 'goose-py' not in p or 'goose-system' in p]

        from goose.server.main import create_app
        import uvicorn
        import asyncio

        app = create_app(secret_key=None, token='test_bearer_token')
        config = uvicorn.Config(app, host='127.0.0.1', port=18081, log_level='error')
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        await asyncio.sleep(1)
        
        yield app
        
        server.should_exit = True
        await task

    async def test_health_endpoint(self, server_with_x_secret_key):
        """Test the health check endpoint"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get('http://127.0.0.1:18080/health')
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert 'timestamp' in data

    async def test_ready_endpoint(self, server_with_x_secret_key):
        """Test the readiness check endpoint"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get('http://127.0.0.1:18080/ready')
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'ready'

    async def test_version_endpoint(self, server_with_x_secret_key):
        """Test the version endpoint"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get('http://127.0.0.1:18080/version')
            assert response.status_code == 200
            data = response.json()
            assert 'version' in data
            assert 'name' in data
            assert data['name'] == 'goose-system'

    async def test_auth_without_credentials(self, server_with_x_secret_key):
        """Test that protected endpoints require authentication"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get('http://127.0.0.1:18080/api/v1/sessions')
            assert response.status_code == 401

    async def test_auth_with_x_secret_key(self, server_with_x_secret_key):
        """Test authentication with X-Secret-Key header"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/sessions',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200

    async def test_auth_with_wrong_x_secret_key(self, server_with_x_secret_key):
        """Test authentication fails with wrong X-Secret-Key"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/sessions',
                headers={'X-Secret-Key': 'wrong_key'}
            )
            assert response.status_code == 401

    async def test_auth_with_bearer_token(self, server_with_bearer_token):
        """Test authentication with Bearer token"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18081/api/v1/sessions',
                headers={'Authorization': 'Bearer test_bearer_token'}
            )
            assert response.status_code == 200

    async def test_auth_with_wrong_bearer_token(self, server_with_bearer_token):
        """Test authentication fails with wrong Bearer token"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18081/api/v1/sessions',
                headers={'Authorization': 'Bearer wrong_token'}
            )
            assert response.status_code == 401

    async def test_list_sessions(self, server_with_x_secret_key):
        """Test listing sessions"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/sessions',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200
            data = response.json()
            assert 'sessions' in data
            assert isinstance(data['sessions'], list)

    async def test_create_and_delete_session(self, server_with_x_secret_key):
        """Test creating and deleting a session via agent/start"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            # Create session
            response = await client.post(
                'http://127.0.0.1:18080/api/v1/agent/start',
                headers={'X-Secret-Key': 'test_secret_key'},
                json={'working_dir': '/tmp'}
            )
            assert response.status_code == 200
            session_data = response.json()
            assert 'id' in session_data
            session_id = session_data['id']
            
            # Get session
            response = await client.get(
                f'http://127.0.0.1:18080/api/v1/sessions/{session_id}',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200
            
            # Delete session
            response = await client.delete(
                f'http://127.0.0.1:18080/api/v1/sessions/{session_id}',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200

    async def test_get_nonexistent_session(self, server_with_x_secret_key):
        """Test getting a session that doesn't exist - creates a new one"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/sessions/nonexistent-id',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            # Session is created automatically if it doesn't exist
            assert response.status_code == 200
            data = response.json()
            assert 'session' in data
            assert 'id' in data['session']

    async def test_delete_nonexistent_session(self, server_with_x_secret_key):
        """Test deleting a session that doesn't exist"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                'http://127.0.0.1:18080/api/v1/sessions/nonexistent-id',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 404

    async def test_agent_endpoints(self, server_with_x_secret_key):
        """Test various agent endpoints"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            # Create a session first
            response = await client.post(
                'http://127.0.0.1:18080/api/v1/agent/start',
                headers={'X-Secret-Key': 'test_secret_key'},
                json={'working_dir': '/tmp'}
            )
            session_id = response.json()['id']
            
            # Test tools endpoint
            response = await client.get(
                f'http://127.0.0.1:18080/api/v1/agent/tools?session_id={session_id}',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200
            
            # Clean up
            await client.delete(
                f'http://127.0.0.1:18080/api/v1/sessions/{session_id}',
                headers={'X-Secret-Key': 'test_secret_key'}
            )

    async def test_config_endpoints(self, server_with_x_secret_key):
        """Test configuration endpoints"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            # Get config
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/config',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200

    async def test_recipe_endpoints(self, server_with_x_secret_key):
        """Test recipe endpoints"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            # List recipes
            response = await client.get(
                'http://127.0.0.1:18080/api/v1/recipes',
                headers={'X-Secret-Key': 'test_secret_key'}
            )
            assert response.status_code == 200
