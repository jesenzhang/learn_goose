---
name: faq
type: global
description: Built-in knowledge base for system FAQs, statistics, and resource recommendations.
allowed-tools: [query_knowledge_base]
---

# FAQ System

The `query_knowledge_base` tool allows you to retrieve pre-defined answers for specific questions or fetch real-time system statistics (like top resources, exhibits).

## Usage Rules
1. **Priority**: Before generating a general answer, check if the user's query matches a built-in FAQ using `query_knowledge_base`.
2. **Exact Match**: The tool relies on precise matching. Pass the user's question directly.
3. **Response**: If the tool returns a result, output it directly to the user. If it returns "None", proceed with your standard reasoning.