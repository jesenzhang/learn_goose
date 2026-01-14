---
name: asset_knowledge_search
description: Search the internal digital asset system with both V1 (ES-based) and V2 (AI-powered) APIs for assets, files, exhibits, documents, libraries, knowledge graph data, statistics, and document content.
allowed-tools: [search_assets, recommend_assets, retrieve_knowledge, search_resource_statistic, search_kg_overview, search_doc, search_exhibits_v2, search_resources_v2]
---

# Asset & Knowledge Search Skill

## API Version Overview

This skill provides **two versions** of search APIs:

| Version | API Type | Use Case | Tools |
|---------|----------|----------|-------|
| **V1** | ES-based (Elasticsearch) | Structured asset management, general file search, system statistics | `search_assets`, `recommend_assets`, `retrieve_knowledge`, `search_resource_statistic`, `search_kg_overview`, `search_doc` |
| **V2** | AI-powered (RAG + LLM) | Intelligent exhibit search, document content search with summaries | `search_exhibits_v2`, `search_resources_v2` |

**Key Difference**: V2 APIs provide better semantic search with LLM-generated summaries, while V1 APIs are better for structured queries and system-wide statistics.

## Instructions
You have access to the enterprise digital asset management system with both V1 and V2 APIs. Choose the appropriate tool based on the user's specific intent.

---

## V1 API Tools (ES-based Search)

### 1. Precise Asset Search (`search_assets`)
Use this when the user clearly specifies **what type of resource** they are looking for, or filters by file format (e.g., "Find documents", "Show me videos", "Search for libraries").
- **Parameters**:
    - `types`: Scope of search. Valid values: `['资产', '资产文件', '专题库']`.
    - `resource_types`: File format. Valid values: `['图片', '视频', '文档', '音频', '3D', '其他']`.
- **Examples**: "Find all video files about 'safety'", "Search for the 'History' library".
- **Action**: Call `search_assets` with specific filters.

### 2. Intelligent Recommendation (`recommend_assets`)
Use this when the user's request is **vague, open-ended**, or explicitly asks for **recommendations**.
- **Examples**: "Recommend some assets about 'AI'", "Help me find something related to 'museums'", "What do you have about 'pandas'?".
- **Action**: Call `recommend_assets`. The system will infer the best types.

### 3. Knowledge Retrieval (`retrieve_knowledge`)
Use this when the user asks a **question** that requires an answer, explanation, or detailed information found *within* the content of documents (RAG).
- **Examples**: "What is the manufacturing process of bronze?", "Explain the history of the artifact", "Summarize the report".
- **Action**: Call `retrieve_knowledge`. This searches the text content of the knowledge base.

### 4. Resource Statistics (`search_resource_statistic`)
Use this when the user asks for **statistics, metrics, or aggregate data** about the asset system.
- **Parameters**:
    - `statistic_type`: The type of statistic (required). Valid values:
        - `'resource_count_by_type'`: Asset count by type
        - `'resource_file_count_by_type'`: File count by asset type
        - `'resource_file_count_by_ext'`: File count by format (jpg, mp4, pdf, etc.)
        - `'resource_library_count'`: Total counts of assets and libraries
        - `'resource_top'`: Top 5 most accessed/downloaded/applied assets
        - `'apply_count'`: Total asset application count
        - `'resource_download_count'`: Total download count
        - `'everything_count'`: Image training library count
        - `'face_count'`: Face training library count
        - `'ocr_type'`: OCR text category count
        - `'resource_growth'`: Asset growth count
    - `start_at`: Start date (optional, default: None)
    - `end_at`: End date (optional, default: None)
- **Examples**: "How many assets do we have?", "What are the most popular files?", "Show me statistics for last month".
- **Action**: Call `search_resource_statistic` with appropriate statistic type.

### 5. Knowledge Graph Overview (`search_kg_overview`)
Use this when the user asks for **knowledge graph statistics** or information about the graph structure.
- **Returns**: Entity types, relationship types, properties, total counts, top entities, and update information.
- **Examples**: "What's in our knowledge graph?", "How many entities are there?", "Show me the graph overview".
- **Action**: Call `search_kg_overview`.

### 6. Document Content Query (`search_doc`)
Use this when the user provides **specific file IDs** and wants to view the actual document content.
- **Parameters**:
    - `resource_file_ids`: Single file ID string or list of file IDs (required)
    - `token`: Authentication token (optional, for restricted content)
- **Examples**: "Show me content of file ID 12345", "Get content for these files: [id1, id2]".
- **Action**: Call `search_doc` with the file IDs.
- **Note**: This tool requires the user to already know the file IDs from previous search results.

---

## V2 API Tools (AI-powered Search)

### 7. Exhibit Search V2 (`search_exhibits_v2`)
**NEW**: Use this when searching for **physical artifacts, museum exhibits, or object collections** with intelligent semantic search.

**When to use V2 vs V1**:
- Use **V2** (`search_exhibits_v2`) for: Physical artifacts, exhibit metadata, object descriptions with semantic understanding
- Use **V1** (`search_assets` with `types=["资产"]`) for: General digital asset management, structured queries

- **Parameters**:
    - `query`: Search keyword (required)
    - `exhibit_ids`: Optional list of specific exhibit IDs for precise search
    - `filters`: Optional filter conditions (e.g., `{"era": "战国", "material": "青铜"}`)
    - `top_k`: Maximum results to return (default: 5)
- **Features**:
    - AI-powered semantic search (understands intent, not just keywords)
    - Automatic reranking for relevance
    - Better handling of natural language queries
- **Examples**:
    - "Find bronze weapons from the Warring States period" → `search_exhibits_v2(query="青铜武器", filters={"era": "战国"})`
    - "Show me jade ornaments" → `search_exhibits_v2(query="玉器装饰品")`
    - "What gold artifacts do you have?" → `search_exhibits_v2(query="金器")`

### 8. Resource Search V2 (`search_resources_v2`)
**NEW**: Use this when searching for **document content, research papers, or detailed knowledge** with AI-generated summaries.

**When to use V2 vs V1**:
- Use **V2** (`search_resources_v2`) for: Document content search with LLM summaries, research papers, knowledge retrieval
- Use **V1** (`retrieve_knowledge`) for: Knowledge graph-based question answering
- Use **V1** (`search_assets` with `types=["资产文件"]`) for: Structured file management

- **Parameters**:
    - `query`: Search keyword (required)
    - `file_ids`: Optional list of specific file IDs for precise search
    - `tags`: Optional list of tags to filter results
    - `top_k`: Maximum results to return (default: 5)
- **Features**:
    - LLM-generated summaries for better context understanding
    - Semantic search that understands research topics
    - Automatic reranking for relevance
- **Examples**:
    - "Research on bronze casting techniques" → `search_resources_v2(query="青铜铸造工艺")`
    - "Historical background of the Han Dynasty" → `search_resources_v2(query="汉代历史背景")`
    - "Documents about the Jade Cabbage" → `search_resources_v2(query="翠玉白菜")`

---

## Parameter Constraints
When using `search_assets`, you **MUST** use the exact string values for lists:

* **`types` (Search Scope)**:
    * `"资产"` (Assets - logical objects)
    * `"资产文件"` (Files - physical files)
    * `"专题库"` (Libraries - collections)
* **`resource_types` (File Format)**:
    * `"图片"`, `"视频"`, `"文档"`, `"音频"`, `"3D"`, `"其他"`

## General Rules
- The tools return a summary view (Markdown) and structured data (Artifacts).
- Use the Markdown view to summarize the answer for the user.
- If the user asks to "show" or "list" items, the client will render the dataset automatically; you just need to introduce it (e.g., "Here are the assets I found...").
- **Do not** make up IDs or filenames. Only use data returned by the tools.

## Examples

### V1 API Examples

**User**: "帮我找一下关于'海昏侯'的文档和图片"
**Assistant**: (Thought: User wants specific file formats.)
**Tool Call**: `search_assets(query="海昏侯", types=["资产文件"], resource_types=["文档", "图片"])`

**User**: "给我推荐一些关于'青铜器'的资源"
**Assistant**: (Thought: User is asking for recommendation/exploration.)
**Tool Call**: `recommend_assets(query="青铜器")`

**User**: "马蹄金是什么时候出土的？"
**Assistant**: (Thought: User asks a factual question requiring knowledge retrieval.)
**Tool Call**: `retrieve_knowledge(query="马蹄金 出土时间")`

**User**: "搜索名为'汉代文化'的专题库"
**Assistant**: (Thought: User specifically mentions '专题库'.)
**Tool Call**: `search_assets(query="汉代文化", types=["专题库"])`

**User**: "我们系统里有多少资产？"
**Assistant**: (Thought: User asks for aggregate statistics.)
**Tool Call**: `search_resource_statistic(statistic_type='resource_library_count')`

**User**: "哪些文件最受欢迎？"
**Assistant**: (Thought: User asks for top accessed/downloaded content.)
**Tool Call**: `search_resource_statistic(statistic_type='resource_top')`

**User**: "显示一下知识图谱的概况"
**Assistant**: (Thought: User wants knowledge graph overview.)
**Tool Call**: `search_kg_overview()`

**User**: "查看文件ID为'abc123'的文档内容"
**Assistant**: (Thought: User provides specific file ID and wants content.)
**Tool Call**: `search_doc(resource_file_ids='abc123')`

**User**: "统计一下上个月的视频文件数量"
**Assistant**: (Thought: User wants file count by format with date range.)
**Tool Call**: `search_resource_statistic(statistic_type='resource_file_count_by_ext', start_at='2024-12-01', end_at='2024-12-31')`

### V2 API Examples (NEW)

**User**: "找一些战国的青铜器藏品"
**Assistant**: (Thought: User wants physical artifacts with specific era and material.)
**Tool Call**: `search_exhibits_v2(query="青铜器", filters={"era": "战国"})`

**User": "我想看玉器类的藏品"
**Assistant**: (Thought: User wants to browse exhibits in a specific category.)
**Tool Call**: `search_exhibits_v2(query="玉器")`

**User**: "有没有关于青铜铸造工艺的研究资料？"
**Assistant**: (Thought: User wants document content with LLM summaries.)
**Tool Call**: `search_resources_v2(query="青铜铸造工艺")`

**User**: "帮我查一下汉代历史背景的相关文档"
**Assistant**: (Thought: User wants research papers/documents with semantic understanding.)
**Tool Call**: `search_resources_v2(query="汉代历史背景")`

**User**: "找一些关于考古的资料"
**Assistant**: (Thought: User wants research documents, could use V2 for better results.)
**Tool Call**: `search_resources_v2(query="考古", tags=["研究", "论文"])`

### Comparison Examples

**User**: "找一些关于剑的藏品"
**Option A (V1 - Structured)**: `search_assets(query="剑", types=["资产"], resource_types=["图片"])`
**Option B (V2 - Semantic)**: `search_exhibits_v2(query="剑")` ← Better for natural language understanding

**User**: "青铜器的制作工艺有什么资料？"
**Option A (V1 - Knowledge Graph)**: `retrieve_knowledge(query="青铜器制作工艺")`
**Option B (V2 - Document Search)**: `search_resources_v2(query="青铜器制作工艺")` ← Better for document content with summaries