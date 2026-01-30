---
name: asset_knowledge_search
description: An advanced search system for digital assets, museum exhibits, documents, and knowledge graphs. Features a tiered search strategy (Simple/Standard/Deep) combining V1 (Elasticsearch-based) and V2 (AI/Semantic-based) APIs.
allowed-tools: [search_assets, recommend_assets, retrieve_knowledge, search_resource_statistic, search_kg_overview, lookup_doc_content, search_exhibits_v2, search_resources_v2, page_content_qa]
---

# Asset & Knowledge Search Skill

## 1. Skill Overview & Strategy Engine

This skill provides access to the enterprise digital asset management system through two API generations (V1 & V2). To maximize relevance, the Agent **MUST** first classify the user's intent into one of three search levels before selecting tools.

### Search Strategy Matrix

| Level | Strategy Name | User Intent | Keyword Strategy | Tool Selection Scope |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | **Simple Search** | Specific file lookup, format filtering, or exact statistics. | **Exact Match**: Use the user's core entity directly. | Single V1 Tool (High Precision). |
| **L2** | **Standard Search** | Browsing topics, finding exhibits with attributes, general exploration. | **Expansion**: Generate 2-3 synonyms or related terms. | V2 Semantic Tools OR V1 Recommendation. |
| **L3** | **Deep Search** | Complex research, historical synthesis, multi-dimensional analysis. | **Multi-Path**: Generate keywords for Core Concept + Historical Context + Tech specs. | **Chain Execution**: Combine V2 (Content) + V1 (Knowledge/Stats). |

---

## 2. V1 API Tools (ES-based: Precision & Statistics)

Use V1 tools when specific filters, exact file types, or system-wide metrics are required.

### `search_assets` (L1/L2)
**Goal**: Precise search for structured assets, specific file formats, or libraries.
* **Parameters**:
    * `query`: Search keywords.
    * `types`: Scope. MUST be one of: `['资产', '资产文件', '专题库']`.
    * `resource_types`: Format. MUST be one of: `['图片', '视频', '文档', '音频', '3D', '其他']`.
* **Best for**: "Find all PDFs about X", "Search the video library".

### `recommend_assets` (L2)
**Goal**: Handling vague requests or explicit requests for suggestions.
* **Parameters**: `query` (topic or keyword).
* **Best for**: "Recommend something about...", "What do you have related to X?".

### `retrieve_knowledge` (L3)
**Goal**: Extracting specific answers from the Knowledge Graph (QA style).
* **Parameters**: `query` (natural language question).
* **Best for**: Factual QA ("When was X excavated?", "What is the size of Y?").

### `search_resource_statistic` (L1)
**Goal**: System metrics and aggregation.
* **Parameters**:
    * `statistic_type`: **Required**. Values: `resource_count_by_type`, `resource_file_count_by_type`, `resource_file_count_by_ext`, `resource_library_count`, `resource_top` (popular), `apply_count`, `resource_download_count`, `everything_count`, `face_count`, `ocr_type`, `resource_growth`.
    * `start_at`, `end_at`: Optional date range (YYYY-MM-DD).

### `search_kg_overview` (L1)
**Goal**: High-level metadata about the Knowledge Graph structure.
* **Best for**: "How many entities are in the graph?", "Show graph schema".

### `lookup_doc_content` (L1)
**Goal**: Reading the full text of a document given a known File ID.
* **Parameters**: `resource_file_ids` (List of IDs).

---

## 3. V2 API Tools (AI-powered: Semantic & Context)

Use V2 tools for natural language understanding, exhibit descriptions, and document summaries.


**CRITICAL RULE for V2**: The `filters` parameter in V2 tools may be unstable. **ALWAYS** incorporate the semantic meaning of the filters into the `query` string itself.


### `search_exhibits_v2` (L2/L3)
**Goal**: Searching for physical **Artifacts** and **Museum Exhibits** using semantic understanding.
* **Parameters**:
    * `query`: **Enriched Semantic Description**. MUST include Era, Material, and Type explicitly (e.g., "Han Dynasty Jade Cup" instead of just "Cup").
    * `filters`: Dictionary for metadata (e.g., `{"era": "战国", "material": "青铜"}`). *Use as a secondary refinement, not the primary filter.*
    * `top_k`: Max results.
* **High Recall Strategy**: If the user asks for "Warring States Bronze Swords", issue the call: `search_exhibits_v2(query="战国时期 青铜剑 兵器", filters={"era": "战国", "material": "青铜"})`.
* **Note**: Better than `search_assets` for finding "things" rather than "files".

### `search_resources_v2` (L2/L3)
**Goal**: Searching for **Intellectual Content** (Papers, Reports, Articles) with AI summaries.
* **Parameters**:
    * `query`: Research topic (e.g., "Bronze casting techniques").
    * `tags`: Optional classification tags.
    * `file_ids`: Narrow down to specific files if known.
* **Note**: Returns LLM-generated summaries ideal for research questions.

---

## 4. Context-Aware Tools

### `page_content_qa`
**Goal**: Answer questions based **only** on the user's current screen content.
* **Parameters**: `question`.
* **Trigger**: "Summarize this page", "Does this page mention X?".

---

## 5. Execution Rules & Constraints

1.  **Strict Enum Types**: When using V1 `search_assets`, you must stick to the allowed list values for `types` and `resource_types`.
2.  **ID Integrity**: Never invent IDs. Only use IDs returned by a previous search step.
3.  **V2 Priority**: If the user uses vague terms like "Show me items about..." or "Info on...", default to V2 tools first for better recall.
4.  **Markdown Output**: Always summarize findings in Markdown tables or lists for readability.

---

## 6. Scenario Examples

### Scenario: Simple Precision Search (Level 1)
**User**: "Find all video files regarding 'Safety Education'."
**Analysis**: Specific format request -> L1 Strategy.
**Actions**:
```python
search_assets(query="Safety Education", types=["资产文件"], resource_types=["视频"])

```

### Scenario: Statistical Query (Level 1)

**User**: "How many new assets were added last month?"
**Analysis**: Metric request -> L1 Strategy.
**Actions**:

```python
search_resource_statistic(statistic_type="resource_growth", start_at="2024-01-01", end_at="2024-01-31")

```

### Scenario: Artifact Browsing (Level 2)

**User**: "I want to see some bronze weapons from the Warring States period."
**Analysis**: Exhibit search with attributes -> L2 Strategy (Standard).
**Keywords**: Query="Bronze Weapon", Filter={era: Warring States}.
**Actions**:

```python
search_exhibits_v2(query="青铜兵器", filters={"era": "战国"})

```

### Scenario: Deep Research Topic (Level 3)

**User**: "Research the evolution of crafting techniques for gold ornaments from the Han Dynasty, including any related papers."
**Analysis**: Complex research request -> L3 Strategy (Deep Search).
**Plan**:

1. Search for physical examples to understand the object types (V2 Exhibits).
2. Search for academic content/papers on the technique (V2 Resources).
3. Cross-reference specific facts (V1 Knowledge).
**Actions**:

```python
# Step 1: Find the artifacts
search_exhibits_v2(query="汉代 金器 装饰品", top_k=5)

# Step 2: Find the literature/techniques
search_resources_v2(query="汉代 金器 制作工艺 掐丝 焊接", tags=["研究", "论文"])

# Step 3: (Optional) Verify specific dates or terms found in previous steps
retrieve_knowledge(query="汉代金饼铸造工艺")

```

### Scenario: Contextual Inquiry

**User**: "Does the current page mention anything about 'Jade'?"
**Analysis**: Screen context -> Context Tool.
**Actions**:

```python
page_content_qa(question="Does this page mention 'Jade'?")

```

