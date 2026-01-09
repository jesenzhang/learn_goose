---
name: knowledge-base
type: global
description: The PRIMARY source of truth. MUST be checked FIRST for system identity, capabilities, status, and troubleshooting. Unified Knowledge Base engine. Retrieves answers from local static files and remote dynamic APIs. Handles identity, capabilities, and real-time system stats.
allowed-tools: [query_knowledge_base, refresh_knowledge_base]
---

# Knowledge Base Engine

This skill acts as the centralized "brain" for system knowledge. It combines pre-defined static FAQs with dynamic data fetched from remote APIs (configured via metadata).

## Available Tools

1.  **`query_knowledge_base(query: str)`**
    * **Use when**: The user asks about:
        * **System Identity**: "Who are you?", "What is this system?"
        * **Capabilities**: "What can you do?", "Help menu".
        * **System Status/Stats**: "Current load", "Top resources", "Deployment logs" (if configured).
        * **General FAQs**: Standard operating procedures defined in the database.
    * **Behavior**: It performs a fuzzy match against the knowledge base. If the match is a "dynamic" item, it automatically executes the configured API request and formats the result.

2.  **`refresh_knowledge_base()`**
    * **Use when**: The user explicitly asks to update the configuration or fetch the latest FAQ data (e.g., "Reload config", "Refresh FAQ").
    * **Behavior**: Forces a reload of both local files and the remote data source.

## Interaction Guidelines for Agent

1.  **Priority Check**: Before writing Python code or generating a generic AI response, **ALWAYS** check `query_knowledge_base` first if the user's request seems like a standard query or system check.
2.  **Direct Output**: If the tool returns a valid answer (not "None"), present it to the user directly.
3.  **Fallback**: If the tool returns "None" (meaning no match found), you should proceed with standard reasoning, planning, or using other specialized skills.
4.  **No Hallucinations**: Do not make up system statistics. If `query_knowledge_base` returns nothing for "system status", simply state that you don't have that information.

## Configuration Reference (For Developers)

The data source supports two types of items:

**1. Static Item:**
```json
{
  "questions": ["Who are you"],
  "type": "static",
  "answer": "I am OpsCommander."
}