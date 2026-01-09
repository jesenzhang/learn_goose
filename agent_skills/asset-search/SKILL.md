---
name: asset-search
description: Search the museum database for exhibits (artifacts) and digital resources (documents/research).
allowed-tools: [search_exhibits, search_resources]
---

# Museum Asset Search

## Instructions
You have access to the museum's internal database. Use the appropriate tool based on the user's intent.

### 1. Searching for Exhibits (`search_exhibits`)
Use this when the user is asking about **physical objects**, artifacts, or items on display.
- **Examples**: "Find Qing dynasty vases", "Where is the Jade Cabbage?", "Show me gold ornaments".
- **Action**: Provide the query keyword. The result will contain metadata about the artifact.

### 2. Searching for Resources (`search_resources`)
Use this when the user is asking for **knowledge, research, papers, or detailed textual descriptions** that might be in documents.
- **Examples**: "Research papers on bronze casting", "Historical background of the Forbidden City", "Detailed description of item X".
- **Action**: Provide the query keyword. The result will contain text segments from documents.

## General Rules
- If the search returns JSON data, parse it and summarize the key information for the user in a natural tone.
- If no results are found, inform the user politely and suggest broadening the search terms.
- **Do not** invent artifacts if the search returns empty.

## Examples

**User**: "帮我找一下关于'马'的藏品"
**Assistant**: (Thought: User wants artifacts.)
**Tool Call**: `search_exhibits(query="马")`

**User**: "我想了解一下清朝陶瓷的烧制工艺资料"
**Assistant**: (Thought: User wants knowledge/documents.)
**Tool Call**: `search_resources(query="清朝陶瓷 工艺")`