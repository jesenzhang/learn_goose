import json
import logging
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from pydantic.types import AwareDatetime

# [关键] 引入我们之前定义的通用 Artifact 协议
from assistant.conversation import CallToolResult
from assistant.core.agent import AgentContext

logger = logging.getLogger(__name__)    

# =============================================================================
# Helper Functions
# =============================================================================

def _calculate_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _normalize_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

# =============================================================================
# Tool Implementations
# =============================================================================

async def save_memory(content: str = None, ctx:AgentContext=None) -> CallToolResult:
    """
    Save important information to long-term memory.
    """
    if ctx == None:
        return CallToolResult.failure("Context is None.")
    
    state, db = ctx.state, ctx.db
    
    content = _normalize_content(content)

    if not state or not db:
        return CallToolResult.failure("Database or State not available.")

    if not content or not content.strip():
        return CallToolResult.failure("Memory content cannot be empty.")

    session_id = state.session_id

    # 1. 去重检查
    try:
        existing_memories = await db.get_memories(session_id, limit=50)
        for mem in existing_memories:
            existing_content = mem.get("content", "")
            if _calculate_similarity(existing_content, content) > 0.85:
                # 重复内容只返回文本提示，不需要 Data Artifact
                return CallToolResult.from_text(f"Memory already exists (skipped): '{content}'")
    except Exception as e:
        logger.warning(f"Deduplication check failed: {e}")

    # 2. 执行保存
    timestamp_str = time.strftime("%Y-%m-%d %H:%M")
    final_content = f"[{timestamp_str}] {content}"

    try:
        success = await db.add_memory(session_id, final_content)

        if success:
            # 成功保存：返回 Artifact，Data 包含结构化信息方便后续使用
            return CallToolResult.from_artifact(
                view=f"✅ Saved to memory: {content}",
                data={
                    "content": final_content,
                    "raw_content": content,
                    "created_at": timestamp_str
                },
                type="text" # 这里虽有 data，但类型归为 text 即可，或者自定义 event
            )
        else:
            return CallToolResult.failure("Database write failed.")

    except Exception as e:
        logger.error(f"Save memory failed: {e}")
        return CallToolResult.failure(str(e))


async def search_memory(query: str = None, ctx:AgentContext=None) -> CallToolResult:
    """
    Search long-term memory for information.
    """
    if ctx == None:
        return CallToolResult.failure("Context is None.")
    
    state, db = ctx.state, ctx.db
    query = _normalize_content(query).strip().lower()

    if not state or not db:
        return CallToolResult.failure("System context missing.")
    if not query:
        return CallToolResult.failure("Query cannot be empty.")

    try:
        matches = []

        # 策略 A: SQL LIKE
        if hasattr(db, "search_memories"):
            matches =await db.search_memories(state.session_id, query)
        
        # 策略 B: 内存过滤
        else:
            all_memories =await db.get_memories(state.session_id, limit=1000)
            for mem in all_memories:
                content = mem.get("content", "").lower()
                if query in content:
                    matches.append(mem)

        if not matches:
            return CallToolResult.from_text(f"No memories found matching '{query}'.")

        # 生成 Artifact
        # View: Markdown List
        view_lines = [f"Found {len(matches)} matches for '{query}':"]
        for m in matches[:10]:
            mem_id = m.get("id", "N/A")
            content = m.get("content", "").replace("\n", " ")
            view_lines.append(f"- [ID:{mem_id}] {content}")

        # Data: 完整数据
        return CallToolResult.from_artifact(
            view="\n".join(view_lines),
            data=matches,
            type="dataset"
        )

    except Exception as e:
        logger.error(f"Search memory failed: {e}")
        return CallToolResult.failure(str(e))


async def list_memories(limit: int = 10,ctx:AgentContext=None) -> CallToolResult:
    """List most recent memories."""
    if ctx == None:
        return CallToolResult.failure("Context is None.")
    
    state, db = ctx.state, ctx.db
    
    if not state or not db:
        return CallToolResult.failure("System context missing.")

    try:
        memories = await db.get_memories(state.session_id, limit=limit)

        if not memories:
            return CallToolResult.from_text("Memory is empty.")

        view_lines = ["**Recent Memories:**"]
        for m in memories:
            mem_id = m.get("id", "N/A")
            view_lines.append(f"- [ID:{mem_id}] {m.get('content')}")

        return CallToolResult.from_artifact(
            view="\n".join(view_lines),
            data=memories,
            type="dataset"
        )
    except Exception as e:
        return CallToolResult.failure(str(e))


async def delete_memory(memory_id: int, ctx:AgentContext=None) -> CallToolResult:
    """
    Delete a specific memory entry by ID.
    """
    if ctx == None:
        return CallToolResult.failure("Context is None.")
    state, db = ctx.state, ctx.db
    if not state or not db:
        return CallToolResult.failure("System context missing.")
    if not memory_id:
        return CallToolResult.failure("Memory ID cannot be empty.")
    try:
        try:
            mid = int(memory_id)
        except ValueError:
            return CallToolResult.failure(f"Invalid memory_id: {memory_id}")

        if hasattr(db, "delete_memory"):
            success =await db.delete_memory(mid)
            if success:
                return CallToolResult.from_text(f"🗑️ Memory ID {mid} deleted.")
            else:
                return CallToolResult.failure(f"Memory ID {mid} not found.")
        else:
            return CallToolResult.failure("Database does not support deletion.")

    except Exception as e:
        return CallToolResult.failure(str(e))


