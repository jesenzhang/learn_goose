# HTTP Backend API Specification

This document describes the HTTP API interface that the `HTTPBackend` expects from a unified database service.

## Overview

The HTTPBackend provides a way to delegate database operations to a centralized HTTP API service. This is useful for:

- **Centralized database access** - All database operations go through a single service
- **Unified authentication** - API keys and authentication managed centrally
- **Audit logging** - All database operations can be logged at the API layer
- **Multi-database support** - The API can abstract multiple database implementations

## Base URL

All endpoints are prefixed with `/api/v1/db`.

## Authentication

The client supports API key authentication via a configurable header. Default:

```
X-API-Key: your-api-key
```

The header name can be configured using the `api_key_header` parameter.

## Common Response Format

All endpoints return JSON in the following format:

### Success Response
```json
{
  "status": "success",
  "data": { ... }
}
```

### Error Response
```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message",
    "details": { ... }
  }
}
```

## Endpoints

### 1. Boot - Initialize Database Schema

Initialize the database with table schemas.

**Endpoint:** `POST /api/v1/db/boot`

**Request:**
```json
{
  "schemas": [
    {
      "table_name": "sessions",
      "schema_sql": [
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_name ON sessions(name);"
      ],
      "pk_field": "id",
      "priority": 0,
      "source": "SessionRepository"
    }
  ]
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "tables_created": ["sessions", "messages"],
    "message": "Database initialized successfully"
  }
}
```

---

### 2. Insert - Create New Record

Insert a new record into a table.

**Endpoint:** `POST /api/v1/db/{table}/insert`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "data": {
    "id": "session-123",
    "name": "My Session",
    "created_at": 1234567890.0
  }
}
```

**Optional:** Include `_transaction_id` for transactional operations:
```json
{
  "data": { ... },
  "_transaction_id": "txn-abc123"
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "id": "session-123",
    "created": true
  }
}
```

**Error:** `409 Conflict` - Duplicate key
```json
{
  "status": "error",
  "error": {
    "code": "DUPLICATE_KEY",
    "message": "Record with this ID already exists"
  }
}
```

---

### 3. Get - Fetch Single Record

Fetch a single record by primary key.

**Endpoint:** `POST /api/v1/db/{table}/get`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "pk_value": "session-123"
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "id": "session-123",
    "name": "My Session",
    "created_at": 1234567890.0
  }
}
```

**Error:** `404 Not Found`
```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Record not found"
  }
}
```

---

### 4. Get Batch - Fetch Multiple Records

Fetch multiple records by primary keys.

**Endpoint:** `POST /api/v1/db/{table}/get-batch`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "pk_values": ["session-123", "session-456", "session-789"]
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": [
    {
      "id": "session-123",
      "name": "My Session"
    },
    {
      "id": "session-456",
      "name": "Another Session"
    }
  ]
}
```

---

### 5. Find - Query with Filters

Find records matching filter conditions.

**Endpoint:** `POST /api/v1/db/{table}/find`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "filters": {
    "status": "active",
    "age": { "$gt": 18 },
    "score": { "$gte": 60, "$lt": 90 },
    "role": { "$in": ["admin", "dev"] },
    "name": { "$like": "%Goose%" }
  },
  "limit": 10,
  "offset": 0
}
```

**Supported Operators:**
- `$eq` - Equal (default when no operator specified)
- `$ne` - Not equal
- `$gt` - Greater than
- `$gte` - Greater than or equal
- `$lt` - Less than
- `$lte` - Less than or equal
- `$in` - In list
- `$like` - SQL LIKE (case-sensitive)
- `$ilike` - SQL ILIKE (case-insensitive, PostgreSQL)

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": [
    { "id": "1", "name": "Record 1" },
    { "id": "2", "name": "Record 2" }
  ]
}
```

---

### 6. Count - Count Records

Count records matching filter conditions.

**Endpoint:** `POST /api/v1/db/{table}/count`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "filters": {
    "status": "active"
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "count": 42
}
```

---

### 7. Update - Update Single Record

Update a record by primary key.

**Endpoint:** `POST /api/v1/db/{table}/update`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "pk_value": "session-123",
  "data": {
    "name": "Updated Session",
    "updated_at": 1234567890.0
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "id": "session-123",
    "updated": true
  }
}
```

---

### 8. Update By - Batch Update

Update multiple records matching filters.

**Endpoint:** `POST /api/v1/db/{table}/update-by`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "filters": {
    "status": "inactive"
  },
  "data": {
    "status": "active",
    "updated_at": 1234567890.0
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "affected_rows": 15
  }
}
```

---

### 9. Upsert - Insert or Update

Insert a record or update if it exists.

**Endpoint:** `POST /api/v1/db/{table}/upsert`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "data": {
    "id": "session-123",
    "name": "My Session",
    "updated_at": 1234567890.0
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "id": "session-123",
    "created": false,
    "updated": true
  }
}
```

---

### 10. Delete - Delete Single Record

Delete a record by primary key.

**Endpoint:** `POST /api/v1/db/{table}/delete`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "pk_value": "session-123"
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "deleted": true
  }
}
```

---

### 11. Delete By - Batch Delete

Delete multiple records matching filters.

**Endpoint:** `POST /api/v1/db/{table}/delete-by`

**URL Parameters:**
- `table` - Table name

**Request:**
```json
{
  "filters": {
    "status": "deleted",
    "created_at": { "$lt": 1234567890.0 }
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "affected_rows": 5
  }
}
```

---

## Transaction Management

### Begin Transaction

Start a new transaction and return a transaction ID.

**Endpoint:** `POST /api/v1/db/transaction/begin`

**Request:**
```json
{}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "transaction_id": "txn-abc123"
}
```

---

### Commit Transaction

Commit a transaction.

**Endpoint:** `POST /api/v1/db/transaction/{transaction_id}/commit`

**URL Parameters:**
- `transaction_id` - Transaction ID from begin

**Request:**
```json
{}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "committed": true
  }
}
```

---

### Rollback Transaction

Rollback a transaction.

**Endpoint:** `POST /api/v1/db/transaction/{transaction_id}/rollback`

**URL Parameters:**
- `transaction_id` - Transaction ID from begin

**Request:**
```json
{}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "data": {
    "rolled_back": true
  }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Malformed request |
| `UNAUTHORIZED` | 401 | Missing or invalid API key |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `DUPLICATE_KEY` | 409 | Primary key conflict |
| `VALIDATION_ERROR` | 422 | Data validation failed |
| `INTERNAL_ERROR` | 500 | Server error |
| `DATABASE_ERROR` | 500 | Database operation failed |

---

## Usage Examples

### Client Configuration

```python
from pho.persistence import init_persistence

# Basic usage
pm = init_persistence("http://localhost:8000")

# With API key
pm = init_persistence("http://localhost:8000?api_key=secret-key")

# With custom configuration
pm = init_persistence(
    "http://localhost:8000?api_key=secret-key&timeout=60&max_retries=5"
)

# Using HTTPS
pm = init_persistence("https://api.example.com?api_key=secret-key")

await pm.boot()
```

### Direct HTTPBackend Usage

```python
from pho.persistence.backends import HTTPBackend

backend = HTTPBackend(
    base_url="https://api.example.com",
    api_key="your-api-key",
    timeout=60.0,
    max_retries=3
)

await backend.boot(schemas)
```

---

## Server Implementation Example (FastAPI)

```python
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import sqlite3

app = FastAPI()

# Store transaction state
transactions = {}

@app.post("/api/v1/db/boot")
async def boot(request: dict):
    schemas = request.get("schemas", [])
    # Create tables from schemas
    for schema in schemas:
        sql = schema["schema_sql"]
        if isinstance(sql, list):
            for s in sql:
                conn.execute(s)
        else:
            conn.execute(sql)
    return {"status": "success", "data": {"tables_created": [s["table_name"] for s in schemas]}}

@app.post("/api/v1/db/{table}/insert")
async def insert(table: str, request: dict, x_api_key: str = Header(None)):
    # Validate API key
    if not validate_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    data = request.get("data")
    # Insert into database
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    conn.execute(sql, list(data.values()))
    conn.commit()
    return {"status": "success", "data": {"id": data.get("id")}}
```

---

## Security Considerations

1. **HTTPS** - Always use HTTPS in production
2. **API Key Management** - Use environment variables or secret management
3. **Rate Limiting** - Implement rate limiting on the API server
4. **Input Validation** - Validate all input parameters
5. **SQL Injection** - Use parameterized queries
6. **Transaction Isolation** - Properly handle concurrent transactions
7. **Audit Logging** - Log all database operations for compliance

---

## Dependencies

The HTTPBackend requires `httpx`:

```bash
pip install httpx
```

Add to `pyproject.toml`:

```toml
dependencies = [
    "httpx>=0.24.0",
]
```
