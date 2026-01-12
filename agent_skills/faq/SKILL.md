---
name: faq
type: global
description: The PRIMARY source of truth. MUST be checked FIRST for system identity, capabilities, status, and troubleshooting. Unified Knowledge Base engine. Retrieves answers from local static files and remote dynamic APIs. Handles identity, capabilities, and real-time system stats.
allowed-tools: [query_knowledge_base]
---

# FAQ System

The `query_knowledge_base` tool allows you to retrieve pre-defined answers for specific questions or fetch real-time system statistics (like top resources, exhibits).

## Usage Rules
1. **Priority**: Before generating a general answer, check if the user's query matches a built-in FAQ using `query_knowledge_base`.
2. **Exact Match**: The tool relies on precise matching. Pass the user's question directly.
3. **Response**: If the tool returns a result, output it directly to the user. If it returns "None", proceed with your standard reasoning.