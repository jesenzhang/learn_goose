# Goose Agent Server Example

This example demonstrates how to run a Goose Agent server with JSONL-based persistence and API key authentication.

## Features

- **JSONL Persistence**: Sessions and recipes stored in JSONL files (no database required)
- **API Key Authentication**: Secure access with `X-Secret-Key` header
- **Full API Support**: All standard Goose Agent endpoints
- **Easy Debugging**: Human-readable JSONL files for troubleshooting

## Directory Structure

```
agent_server/
├── server.py          # Example server with JSONL persistence
├── client.py          # Example client with API key auth
├── data/
│   ├── sessions/      # Session storage (JSONL files)
│   └── recipes/       # Recipe storage (YAML files)
└── README.md          # This file
```

## Quick Start

### 1. Install Dependencies

```bash
# Server dependencies
pip install aiohttp pyyaml

# Client dependencies
pip install requests
```

### 2. Start the Server

```bash
# Without authentication (development)
python server.py --port 8080

# With authentication (production)
python server.py --port 8080 --secret-key your-secret-key

# Create sample recipe
python server.py --create-sample
```

### 3. Use the Client

```bash
# Health check
python client.py --health

# List sessions
python client.py --sessions

# Run demo
python client.py --demo --secret-key your-secret-key
```

## API Endpoints

### Public Endworks (No Authentication)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/version` | Version info |

### Protected Endworks (Require `X-Secret-Key`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sessions` | List sessions |
| POST | `/api/v1/sessions` | Create session |
| GET | `/api/v1/sessions/{id}` | Get session |
| DELETE | `/api/v1/sessions/{id}` | Delete session |
| GET | `/api/v1/recipes` | List recipes |
| GET | `/api/v1/recipes/{id}` | Get recipe |
| POST | `/api/v1/recipes` | Save recipe |
| POST | `/api/v1/agent/start` | Start agent |
| POST | `/api/v1/agent/call_tool` | Call tool |
| GET | `/api/v1/config` | Get config |
| PUT | `/api/v1/config` | Update config |

## Example Usage

### cURL Examples

```bash
# Health check (public)
curl http://localhost:8080/health

# List sessions (requires auth)
curl -H "X-Secret-Key: my-secret-key" \
  http://localhost:8080/api/v1/sessions

# Create session
curl -X POST -H "X-Secret-Key: my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"working_dir": "/tmp", "name": "My Session"}' \
  http://localhost:8080/api/v1/sessions

# Start agent
curl -X POST -H "X-Secret-Key: my-secret-key" \
  -d '{"working_dir": "/tmp"}' \
  http://localhost:8080/api/v1/agent/start
```

### Python Client Examples

```python
from client import GooseAgentClient

# Initialize client
client = GooseAgentClient(
    base_url="http://localhost:8080",
    secret_key="my-secret-key"
)

# Health check
health = client.health_check()

# Create session
session = client.create_session(
    working_dir="/tmp",
    name="My Session"
)

# Call tool
result = client.call_tool(
    session_id="session_xxx",
    tool_name="read_file",
    arguments={"path": "/tmp/test.txt"}
)
```

## Using Full FastAPI Server

For production use, you can use the full FastAPI server from `goose.server`:

```bash
# Install full server dependencies
pip install fastapi uvicorn

# Run server with authentication
python -m goose.server.main \
  --host 0.0.0.0 \
  --port 8080 \
  --secret-key your-secret-key
```

## Sample Recipe

Create a `hello-agent.yaml` recipe:

```yaml
version: 1.0.0
title: Hello World Agent
description: A simple agent that says hello
instructions: |
  You are a friendly assistant.
  Greet the user and introduce yourself.
parameters:
  - key: name
    input_type: string
    requirement: optional
    description: Your name
```

Save it with the client:
```bash
python client.py --save-recipe hello-agent.yaml
```

## Troubleshooting

### Session Not Found
```
{"error": "Session not found", "status": 404}
```
Check that the session ID exists by listing sessions first.

### Missing Authentication
```
{"error": "Missing X-Secret-Key header", "status": 401}
```
Add the `X-Secret-Key` header to your request.

### Invalid API Key
```
{"error": "Invalid API key", "status": 401}
```
Verify the secret key matches what was configured on the server.

## Data Location

- **Sessions**: `data/sessions/{session_id}.jsonl`
- **Recipes**: `data/recipes/{recipe_id}.yaml`

You can view and edit these files directly for debugging.

## Next Steps

1. **Add LLM Provider**: Configure OpenAI or Anthropic in the config
2. **Add Extensions**: Enable MCP extensions for additional tools
3. **Use Full Server**: Switch to `goose.server` for production
4. **Add Persistence**: Use SQL backend for production databases
