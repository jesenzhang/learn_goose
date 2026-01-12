# Pho Documentation

Welcome to the Pho framework documentation. This page provides an overview of all available documentation.

## Getting Started

- [README](../README.md) - Project overview, installation, and quick start guide

## Core Documentation

### Architecture
- [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) - Agent system architecture and design patterns

### Multi-User Support
- [MULTI_USER.md](MULTI_USER.md) - Multi-user support guide
  - User authentication and authorization
  - Session isolation and collaboration
  - Database migration instructions
  - Code examples

- [AUTH_API.md](AUTH_API.md) - Authentication API reference
  - User registration and login
  - Token management
  - Session collaboration API
  - Error codes and examples

### Persistence Layer
- [persistence_http_api_spec.md](persistence_http_api_spec.md) - HTTP backend API specification
  - API endpoints for database operations
  - Request/response formats
  - Transaction management

### Testing
- [TEST_REPORT_CORRECTED.md](TEST_REPORT_CORRECTED.md) - Honest performance report
- [TEST_REPORT.md](TEST_REPORT.md) - Test results and analysis

## Quick Links

### For Users
- [Installation Guide](../README.md#installation)
- [Quick Start](../README.md#quick-start)
- [Multi-User Setup](MULTI_USER.md#database-migration)

### For Developers
- [Project Structure](../README.md#project-structure)
- [Running Tests](../README.md#running-tests)
- [API Usage Examples](../README.md#api-usage-examples)

### API Reference
- [Authentication API](AUTH_API.md)
- [Agent API](../README.md#api-usage-examples)
- [Workflow API](../README.md#workflow-system)

## Key Topics

### Agent Styles
- **MINIMAL** - Simple LLM + tools
- **REACTIVE** - Event-driven streaming
- **REASONING** - Thought → Action → Observation
- **SKILL_BASED** - Intent → LLM → Tools
- **ORCHESTRATED** - DAG workflow orchestration

See [README](../README.md#available-agent-styles) for details.

### Multi-User Features
- User authentication with tokens
- Role-based access control (RBAC)
- Session isolation per user
- Session collaboration (sharing)
- User-scoped queries

See [MULTI_USER.md](MULTI_USER.md) for details.

### Database Support
- SQLite (local development)
- PostgreSQL (production)
- HTTP API backend (remote database)

See [persistence_http_api_spec.md](persistence_http_api_spec.md) for HTTP backend.

## Contributing

Contributions are welcome! Please read the project structure and testing guidelines before submitting PRs.

## License

Apache-2.0 (inherited from goose-py)
