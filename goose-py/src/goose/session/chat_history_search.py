# goose-py/chat_history_search.py
import json
from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field
import aiosqlite

from ..conversation import MessageContent, TextContent

class ChatRecallMessage(BaseModel):
    """搜索结果中的单条消息摘要"""
    role: str
    content: str
    timestamp: str

class ChatRecallResult(BaseModel):
    """按 Session 聚合的搜索结果"""
    session_id: str
    session_description: str = ""
    session_working_dir: str
    last_activity: str
    total_messages_in_session: int
    messages: List[ChatRecallMessage]

class ChatRecallResults(BaseModel):
    results: List[ChatRecallResult]
    total_matches: int

class ChatHistorySearch:
    def __init__(
        self,
        db_pool, # 传入 session.py 中的 DatabasePool
        query: str,
        limit: int = 10,
        exclude_session_id: Optional[str] = None
    ):
        self.pool = db_pool
        self.query = query
        self.limit = limit
        self.exclude_session_id = exclude_session_id

    async def execute(self) -> ChatRecallResults:
        keywords = [f"%{k.lower()}%" for k in self.query.split()]
        if not keywords:
            return ChatRecallResults(results=[], total_matches=0)

        # 1. 构建 SQL
        # 使用 json_extract 查找 content 数组中 type='text' 的元素的 text 字段
        # 注意：这依赖 SQLite 的 JSON 支持
        sql = """
            SELECT 
                s.id as session_id,
                s.name as session_description, -- Rust 用 description, 我们暂用 name
                s.working_dir,
                s.created_at,
                m.role,
                m.content_json,
                m.timestamp
            FROM messages m
            INNER JOIN sessions s ON m.session_id = s.id
            WHERE 
        """
        
        conditions = []
        for _ in keywords:
            # 查找 content_json 数组中任意元素的 text 字段匹配关键词
            # SQLite JSON 查询比较复杂，简化逻辑：直接查 JSON 文本
            # 严谨做法是用 json_tree/json_each，但直接 LIKE 文本性能更好且兼容性更强
            conditions.append("LOWER(m.content_json) LIKE ?")
        
        sql += f"({' OR '.join(conditions)})"
        params = list(keywords)

        if self.exclude_session_id:
            sql += " AND s.id != ?"
            params.append(self.exclude_session_id)

        sql += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(self.limit)

        # 2. 执行查询
        conn = await self.pool.get_connection()
        async with conn.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()

        # 3. 处理结果
        # Group by Session ID
        grouped = {} # session_id -> {meta, messages: []}
        
        for row in rows:
            sid = row['session_id']
            if sid not in grouped:
                grouped[sid] = {
                    'description': row['session_description'],
                    'working_dir': row['working_dir'],
                    'created_at': row['created_at'], # unused
                    'messages': []
                }
            
            # 解析 content
            try:
                content_list = json.loads(row['content_json'])
                text_parts = []
                for item in content_list:
                    # 简单提取文本用于展示
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif item.get('type') == 'toolRequest':
                        name = item.get('toolCall', {}).get('name', 'unknown')
                        text_parts.append(f"[Tool: {name}]")
                
                full_text = "\n".join(text_parts)
                if full_text: # 只有包含文本才展示
                    grouped[sid]['messages'].append(ChatRecallMessage(
                        role=row['role'],
                        content=full_text,
                        timestamp=str(row['timestamp'])
                    ))
            except:
                continue

        # 4. 统计 Session 总消息数并构建最终结果
        final_results = []
        total_matches = 0
        
        for sid, data in grouped.items():
            if not data['messages']:
                continue
                
            # 查询该 Session 总消息数
            async with conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (sid,)) as c:
                count = (await c.fetchone())[0]
            
            # 排序消息
            data['messages'].sort(key=lambda x: x.timestamp)
            last_activity = data['messages'][-1].timestamp
            
            final_results.append(ChatRecallResult(
                session_id=sid,
                session_description=data['description'],
                session_working_dir=data['working_dir'],
                last_activity=last_activity,
                total_messages_in_session=count,
                messages=data['messages']
            ))
            total_matches += len(data['messages'])

        # 按最后活动时间倒序
        final_results.sort(key=lambda x: x.last_activity, reverse=True)

        return ChatRecallResults(results=final_results, total_matches=total_matches)