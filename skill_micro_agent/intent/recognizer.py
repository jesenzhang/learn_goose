"""
Intent Recognizer - LLM-based intent recognition.
Refactored to be stateless (dependency on external state storage).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from skill_micro_agent.providers.base import BaseLLM
from skill_micro_agent.conversation import Message, Role, TextContent

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
        self.intents = intents

    def build(
        self,
        user_input: str,
        current_intent: Optional[str] = None,
        history_entities: Optional[Dict[str, Any]] = None,
        background_info: str = ""
    ) -> str:
        if history_entities is None:
            history_entities = {}
        
        return f"""# Role
You are an expert in intent recognition and slot filling.

# Task
Analyze the user input and:
1. Identify which intent matches the user's goal
2. Extract relevant slots (parameters)
3. Check if all required slots are present

# Intent Definitions
{self._format_intents()}

# Context
- Active Multi-turn Intent: {current_intent or "None"}
- Known Entities: {json.dumps(history_entities, ensure_ascii=False)}
- Background Info: {background_info}

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
    
    def _format_intents(self) -> str:
        parts = []
        for intent in self.intents:
            slots_desc = []
            for slot in intent.slots:
                req = "REQUIRED" if slot.required else "optional"
                slots_desc.append(f"  - {slot.name}: {slot.description} [{req}]")
            parts.append(f"## {intent.name}\n{intent.description}\nSlots:\n" + "\n".join(slots_desc))
        return "\n".join(parts)


class IntentRecognizer:
    def __init__(self, intents: List[IntentDefinition], llm: BaseLLM):
        self.intents = intents
        self._intent_map = {i.name: i for i in intents}
        self.llm_client = llm
        self.prompt_builder = PromptBuilder(intents)

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
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"): text = text[4:]
            
            data = json.loads(text.strip())
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