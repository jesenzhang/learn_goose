"""
Intent Recognizer - LLM-based intent recognition.
Refactored to be stateless (dependency on external state storage).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime,timezone

from ..providers.base import BaseLLM
from ..conversation import Message, Role, TextContent
from json_repair import repair_json
from .defaults import ADHOC_INTENT

# Import from the unified models file
from .models import (
    IntentDefinition,
    IntentResult,
    MultiIntentResult,
    IntentSession,
)
logger = logging.getLogger(__name__)

class PromptBuilder:
    """Builds prompts for intent recognition."""
    def __init__(self, intents: List[IntentDefinition]):
        self.user_intents = intents

    def build(
        self,
        user_input: str,
        current_intent: Optional[str] = None,
        history_entities: Optional[Dict[str, Any]] = None,
        background_info: str = ""
    ) -> str:
        if history_entities is None:
            history_entities = {}
        # [新增] 获取当前时间
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %A %Z%z") # 2023-10-27 Friday UTC+0000
        return f"""# Role
You are an intelligent Task Planner.
Your goal is to break down the user's request into a sequence of executable steps (Plan).

# Strategy
1. **Analyze**: Break the user input into logical steps.
2. **Match**: For each step, try to match it with a [Defined Intent] from the list below.
3. **Fallback**: If a step does NOT match any specific intent, use the [System Capability] `adhoc_execution`.
4. **Sequence**: Return a logical LIST of intents.

# Defined Intents (Strict Matching)
{self._format_intents(self.user_intents)}

# System Capability (General Purpose)
## {ADHOC_INTENT.name}
Description: {ADHOC_INTENT.description}
Slots:
{self._format_slots(ADHOC_INTENT)}

# Context Info
- **Current Date**: {current_time}
- Active Intent: {current_intent or "None"}
- Known Entities: {json.dumps(history_entities or {}, ensure_ascii=False)}
- Background: {background_info}

# Few-Shot Examples (Hybrid Planning)

User: "搜索关于澳门的文档，然后写一篇介绍文章"
Plan:
{{
    "thought": "Step 1: Search documents (Defined). Step 2: Write article (Undefined/Ad-hoc).",
    "intents": [
        {{
            "intent": "search_documents",
            "status": "ready",
            "entities": {{ "keywords": "澳门" }}
        }},
        {{
            "intent": "adhoc_execution",
            "status": "ready",
            "entities": {{ 
                "instruction": "基于刚才搜索到的澳门文档，写一篇介绍文章",
                "context_source": "search_result"
            }}
        }}
    ],
    "primary_intent": "search_documents"
}}

User: "帮我找一下战国青铜器"
Plan:
{{
    "thought": "Single step, strict match found.",
    "intents": [
        {{
            "intent": "search_exhibits",
            "status": "ready",
            "entities": {{ "keywords": "青铜器", "filters": {{ "era": "战国" }} }}
        }}
    ]
}}

User: "总结一下今天的对话"
Plan:
{{
    "thought": "No specific search intent matches 'summarize'. Use adhoc.",
    "intents": [
        {{
            "intent": "adhoc_execution",
            "status": "ready",
            "entities": {{ "instruction": "总结今天的对话内容" }}
        }}
    ]
}}

# User Input
{user_input}

# Output Format
Return valid JSON only:
{{
    "intents": [
        {{
            "intent": "intent_name",
            "confidence": 0.95,
            "status": "ready" | "incomplete",
            "entities": {{"slot_name": "value"}},
            "missing_slots": ["slot1"],
            "reply_to_user": "follow up question",
            "thought": "reasoning"
        }}
    ],
    "primary_intent": "intent_name"
}}
"""
    # def _format_intents(self) -> str:
    #     out = []
    #     for i in self.intents:
    #         slots = []
    #         for s in i.slots:
    #             req = "REQ" if s.required else "OPT"
    #             # Serialize Python type to string for Prompt
    #             type_str = s.data_type.__name__ if isinstance(s.data_type, type) else str(s.data_type)
    #             opts = f" Options:{s.options}" if s.options else ""
    #             slots.append(f"- {s.name} ({type_str}): {s.description} [{req}]{opts}")
            
    #         slots_txt = "\n".join(slots) if slots else "(no slots)"
    #         out.append(f"## {i.name}\n{i.description}\nSlots:\n{slots_txt}")
    #     return "\n".join(out)
    
    def _format_slots(self, intent: IntentDefinition) -> str:
        """Helper to format slots for a single intent."""
        slots_desc = []
        for slot in intent.slots:
            req = "REQUIRED" if slot.required else "optional"
            slots_desc.append(f"  - {slot.name}: {slot.description} [{req}]")
        return "\n".join(slots_desc)

    def _format_intents(self, intents: List[IntentDefinition]) -> str:
        parts = []
        for intent in intents:
            parts.append(f"## {intent.name}\n{intent.description}\nSlots:\n{self._format_slots(intent)}")
        return "\n".join(parts)
    

class IntentRecognizer:
    def __init__(self, intents: List[IntentDefinition], llm: BaseLLM):
        self.user_intents = intents
        self._intent_map = {i.name: i for i in intents}
        self._intent_map[ADHOC_INTENT.name] = ADHOC_INTENT
        self.llm_client = llm
        self.prompt_builder = PromptBuilder(self.user_intents)

    async def recognize(
        self,
        user_input: str,
        session_state: Dict[str, Any],
        background_info: str = ""
    ) -> Tuple[MultiIntentResult, Dict[str, Any]]:
        """
        Recognize intent using external state.
        Returns: (Result, Updated_State_Dict)
        """
        # Rehydrate Session
        session = IntentSession(**session_state) if session_state else IntentSession(session_id="temp")
        
        # === [新增] Fast Path: 关键词硬匹配 ===
        # 遍历所有意图，检查是否有 keywords 配置
        for intent_def in self.user_intents:
            # 假设 IntentDefinition 模型里加了 keywords: List[str] 字段
            triggers = getattr(intent_def, "keywords", []) 
            for kw in triggers:
                if kw in user_input:
                    logger.info(f"🚀 Fast Path matched: '{kw}' -> {intent_def.name}")
                    # 直接构造一个高置信度的结果，跳过 LLM
                    fast_result = MultiIntentResult(
                        intents=[IntentResult(
                            intent=intent_def.name,
                            confidence=1.0,
                            status="ready", # 通常关键词触发的意图不需要槽位或由后续步骤填充
                            entities={}
                        )],
                        primary_intent=intent_def.name
                    )
                    # 更新 Session (如果有必要)
                    self._update_session_logic(session, fast_result)
                    return fast_result, session.model_dump()
        
        # === 2. Slow Path: LLM Recognition (原逻辑) ===
            
        prompt = self.prompt_builder.build(
            user_input, session.current_intent, session.collected_slots, background_info
        )

        try:
            response = await self._call_llm(prompt)
            result = self._parse_response(response, session)
        except Exception as e:
            logger.error(f"Recognition failed: {e}")
            return MultiIntentResult(intents=[]), session.model_dump()

        # Update Logic
        self._update_session_logic(session, result)
        
        return result, session.model_dump()

    async def _call_llm(self, prompt: str) -> str:
        messages = [Message.user(prompt)]
        full_content = ""
        try:
            # [FIXED] 必须先 await create() 方法拿到 stream 对象
            async for partial_msg, _ in self.llm_client.astream(messages=messages):
                if partial_msg and partial_msg.content:
                    # 3. Extract text content
                    for item in partial_msg.content:
                        if isinstance(item, TextContent):
                            full_content += item.text
                    
        except Exception as e:
            logger.error(f"LLM API Error during recognition: {e}")
            raise
            
        return full_content

    def _parse_response(self, text: str, session: IntentSession) -> MultiIntentResult:
        try:
            if "<thinking>" in text:
                text = text.split("</thinking>")[-1]
            
            # [优化] 使用 json_repair 自动修复并解析
            # 它可以处理缺少引号、尾部逗号、Markdown 包裹等常见错误
            data = json.loads(repair_json(text))
            
            if isinstance(data, list):
                # 这种情况下通常 LLM 只返回了 intent 列表
                data = {"intents": data, "primary_intent": data[0].get("intent") if data else None}
                
            raw_list = data.get("intents", [])
            if not raw_list and "intent" in data: raw_list = [data]

            results = []
            for raw in raw_list:
                results.append(self._process_single(raw, session))
            
            return MultiIntentResult(intents=results, primary_intent=data.get("primary_intent"))
        except Exception as e:
            logger.error(f"Parse error: {e}. Raw: {text[:100]}...")
            return MultiIntentResult(intents=[])

    def _process_single(self, raw: Dict, session: IntentSession) -> IntentResult:
        name = raw.get("intent", "unknown")
        new_slots = raw.get("entities", {})
        
        # Merge slots
        if session.current_intent == name:
            merged = {**session.collected_slots, **new_slots}
        else:
            merged = new_slots

        # Validate Completeness
        idef = self._intent_map.get(name)
        missing = []
        status = "ready"
        if idef:
            for s in idef.get_required_slots():
                if s.name not in merged or not merged[s.name]:
                    missing.append(s.name)
            if missing: status = "incomplete"

        return IntentResult(
            intent=name,
            confidence=raw.get("confidence", 0.0),
            status=status,
            entities=merged,
            missing_slots=missing,
            reply_to_user=raw.get("reply_to_user"),
            thought=raw.get("thought", "")
        )

    def _update_session_logic(self, session: IntentSession, result: MultiIntentResult) -> None:
        if not result.intents: return
        
        incomplete = result.incomplete_intents
        if incomplete:
            p = incomplete[0]
            session.current_intent = p.intent
            session.collected_slots = p.entities
        elif result.ready_intents:
            session.clear_intent() # Done
        
        session.last_updated = time.time()