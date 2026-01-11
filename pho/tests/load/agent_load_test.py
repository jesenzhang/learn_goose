"""
Load testing script for Pho API using Locust.

Tests concurrent request handling, latency, and throughput.

Usage:
    locust -f tests/load/agent_load_test.py --host=http://localhost:8000
    # Or headless mode:
    locust -f tests/load/agent_load_test.py --headless --host=http://localhost:8000 --users=100 --spawn-rate=10
"""

import time
import json
import random
from locust import HttpUser, task, between, events
from locust.stats import stats_printer


# ============================================================================
# Test Data
# ============================================================================

TEST_MESSAGES = [
    "Hello, how are you?",
    "What's the weather like?",
    "Tell me a joke.",
    "Explain quantum computing.",
    "Write a haiku.",
    "What's the capital of France?",
    "Calculate 25 * 37",
    "Summarize the French Revolution.",
]

AGENT_STYLES = ["minimal", "reactive", "reasoning", "skill_based", "orchestrated"]


# ============================================================================
# Load Test User
# ============================================================================

class PhoApiUser(HttpUser):
    """
    Simulates a user interacting with the Pho API.

    Tasks:
    - Health check
    - List agent styles
    - Chat (non-streaming)
    - Session management
    """

    # Wait time between tasks (in seconds)
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a user starts."""
        # Initialize session
        self.session_id = None
        self.client.verify = False  # Skip SSL verification for local testing

    @task(5)
    def chat_non_streaming(self):
        """Send a chat request (non-streaming)."""
        style = random.choice(AGENT_STYLES)
        message = random.choice(TEST_MESSAGES)

        with self.client.post(
            "/api/v1/agent/chat",
            json={
                "message": message,
                "style": style,
                "stream": False,
            },
            catch_response=True,
            name="/api/v1/agent/chat",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Validate response structure
                if "text" not in data or "status" not in data:
                    response.failure("Invalid response structure")
                else:
                    response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(3)
    def chat_streaming(self):
        """Send a chat request (streaming)."""
        style = random.choice(AGENT_STYLES)
        message = random.choice(TEST_MESSAGES)

        with self.client.post(
            "/api/v1/agent/chat/stream",
            json={
                "message": message,
                "style": style,
                "stream": True,
            },
            catch_response=True,
            name="/api/v1/agent/chat/stream",
        ) as response:
            if response.status_code == 200:
                # For streaming, just check if we get a response
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)
    def list_sessions(self):
        """List all sessions."""
        with self.client.get(
            "/api/v1/agent/sessions",
            catch_response=True,
            name="/api/v1/agent/sessions",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def get_agent_styles(self):
        """Get available agent styles."""
        with self.client.get(
            "/api/v1/agent/styles",
            catch_response=True,
            name="/api/v1/agent/styles",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def health_check(self):
        """Health check endpoint."""
        with self.client.get(
            "/api/v1/agent/health",
            catch_response=True,
            name="/api/v1/agent/health",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


# ============================================================================
# Workflow Load Test User
# ============================================================================

class WorkflowUser(HttpUser):
    """
    Simulates a user interacting with workflow endpoints.
    """

    wait_time = between(2, 5)

    @task(3)
    def list_workflows(self):
        """List workflows."""
        with self.client.get(
            "/api/v1/workflows/",
            catch_response=True,
            name="/api/v1/workflows/",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)
    def create_workflow(self):
        """Create a new workflow."""
        workflow_data = {
            "nodes": [
                {"id": "1", "data": {"type": "entry", "label": "Start"}},
                {"id": "2", "data": {"type": "llm", "label": "LLM"}},
                {"id": "3", "data": {"type": "exit", "label": "End"}},
            ],
            "edges": [
                {"id": "e1", "source": "1", "target": "2"},
                {"id": "e2", "source": "2", "target": "3"},
            ],
        }

        with self.client.post(
            "/api/v1/workflows/",
            json={
                "title": f"Test Workflow {time.time()}",
                "workflow": workflow_data,
            },
            catch_response=True,
            name="/api/v1/workflows/ [POST]",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def validate_workflow(self):
        """Validate a workflow."""
        workflow_data = {
            "nodes": [{"id": "1", "data": {"type": "entry"}}],
            "edges": [],
        }

        with self.client.post(
            "/api/v1/workflows/validate",
            json=workflow_data,
            catch_response=True,
            name="/api/v1/workflows/validate",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


# ============================================================================
# Custom Event Handlers for Metrics
# ============================================================================

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """
    Custom request handler for additional metrics.

    Logs:
    - Slow requests (> 1s)
    - Failed requests
    - Response time percentiles
    """
    if exception:
        print(f"❌ Request failed: {name} - {exception}")
    elif response_time > 1000:
        print(f"⚠️ Slow request: {name} - {response_time}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops."""
    print("\n" + "=" * 60)
    print("Load Test Complete")
    print("=" * 60)

    if environment.stats.total.fail_ratio > 0.05:
        print(f"⚠️ High failure rate: {environment.stats.total.fail_ratio:.1%}")
    else:
        print(f"✅ Acceptable failure rate: {environment.stats.total.fail_ratio:.1%}")

    if environment.stats.total.avg_response_time > 500:
        print(f"⚠️ High avg response time: {environment.stats.total.avg_response_time:.0f}ms")
    else:
        print(f"✅ Good avg response time: {environment.stats.total.avg_response_time:.0f}ms")

    rps = environment.stats.total.total_rps
    print(f"📊 Throughput: {rps:.1f} requests/second")
    print(f"📊 Total requests: {environment.stats.total.num_requests}")
    print("=" * 60 + "\n")


# ============================================================================
# Standalone Runner (for use without locust CLI)
# ============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Pho API Load Test")
    print("=" * 60)
    print("\nUsage:")
    print("  locust -f tests/load/agent_load_test.py --host=http://localhost:8000")
    print("\nHeadless mode:")
    print("  locust -f tests/load/agent_load_test.py --headless \\")
    print("    --host=http://localhost:8000 --users=100 --spawn-rate=10 \\")
    print("    --run-time=1m")
    print("=" * 60)

    sys.exit(0)
