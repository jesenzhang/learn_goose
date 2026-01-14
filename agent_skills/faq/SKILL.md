---
name: faq
type: global
description: Knowledge Base for common questions and system statistics. Retrieves pre-defined answers from local files and real-time data from remote APIs. Used when user asks about system information, top resources, or standard operating procedures.
allowed-tools: [query_faq]
---

# FAQ System

The `query_faq` tool allows you to retrieve pre-defined answers for specific questions or fetch real-time system statistics (like top resources, exhibits).

## Usage
1. **When to use**: Use when responding to common questions about system capabilities, resources, or procedures
2. **Exact Match**: The tool relies on precise matching. Pass the user's question directly.
3. **Response**: If the tool returns a result, output it directly to the user. If it returns "None", proceed with your standard reasoning.