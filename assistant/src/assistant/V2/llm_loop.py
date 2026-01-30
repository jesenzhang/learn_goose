"""LLM main loop extracted for V2."""

import asyncio
import logging
from typing import List, Optional

from ...conversation import (
    Message,
    Role,
    TextContent,
    ToolRequest,
    ThinkingContent,
    RedactedThinkingContent,
)
from ..events import EventType
from ..state import AgentStatus
from ..agent import ThinkingTracker, DEEP_THINKING_INSTRUCTION, _strip_deep_thinking_instruction

logger = logging.getLogger(__name__)


class LLMLoop:
    """LLM main loop extracted from legacy agent."""

    def __init__(self, agent, tool_executor):
        self._agent = agent
        self._tool_executor = tool_executor

    async def run(self, state, gen, req_ctx, *, run_id: str, user_id: Optional[int]):
        """Run the main LLM loop until the state exits RUNNING."""
        emit_kwargs = {"session_id": state.session_id, "run_id": run_id, "user_id": user_id}
        while state.status == AgentStatus.RUNNING:
            await asyncio.sleep(0.01)

            # ==============================
            # [Truncation Integration] 检查并应用消息压缩
            # ==============================
            conv = self._agent._get_conversation(state)
            if self._agent.truncation_manager and hasattr(conv, "check_and_apply_truncation"):
                system_prompt = self._agent._build_system_prompt(state, gen, req_ctx)
                tools = self._agent._get_tools_schema(state, gen)

                truncated = await conv.check_and_apply_truncation(
                    system_prompt=system_prompt,
                    tools=tools,
                )

                if truncated:
                    self._agent._sync_history_from_conversation(state)
                    logger.info("✅ Truncation applied and conversation compacted")

            # 1. Build System Prompt & Update Conversation
            prompt = self._agent._build_system_prompt(state, gen, req_ctx)
            conv = self._agent._get_conversation(state)
            conv.update_system_prompt(prompt)

            # 2. 准备 LLM 推理消息
            deep_thinking_instruction = DEEP_THINKING_INSTRUCTION if req_ctx.deep_thinking else None

            input_messages = conv.for_llm(
                deep_thinking=req_ctx.deep_thinking,
                deep_thinking_instruction=deep_thinking_instruction,
            )
            if not req_ctx.deep_thinking:
                removed = False
                for msg in input_messages:
                    if msg.role == Role.USER:
                        for c in msg.content:
                            if isinstance(c, TextContent):
                                c.text, changed = _strip_deep_thinking_instruction(c.text)
                                removed = removed or changed
                if removed:
                    logger.warning(
                        "deep_thinking_instruction removed from input_messages (deep_thinking=False)"
                    )

            # 3. 获取工具 schema
            tools = self._agent._get_tools_schema(state, gen)
            logger.info(
                f"🔧 Available tools count: {len(tools) if tools else 0}, active_skill: {state.active_skill}"
            )

            # 4. Call BaseLLM
            full_content_text = ""
            received_tool_requests: List[ToolRequest] = []
            parse_state = "normal"  # normal, check_open, thinking, check_close
            tag_buffer = ""

            thinking = ThinkingTracker(lambda et, data: self._agent._emit_event(et, data, **emit_kwargs))
            async with self._agent.event_scope(
                EventType.TOKEN_START,
                EventType.TOKEN_END,
                **emit_kwargs,
            ):
                try:
                    async for partial_msg, usage in gen.llm.astream(
                        messages=input_messages,
                        tools=tools or None,
                    ):
                        if partial_msg and partial_msg.content:
                            for c in partial_msg.content:
                                if isinstance(c, (ThinkingContent, RedactedThinkingContent)):
                                    await thinking.start()
                                    await thinking.token(c.thinking)
                                elif isinstance(c, TextContent):
                                    text_chunk = c.text

                                    if not req_ctx.deep_thinking:
                                        await thinking.end()
                                        await self._agent._emit_event(EventType.TOKEN, c.text, **emit_kwargs)
                                        full_content_text += c.text
                                        continue

                                    for char in text_chunk:
                                        if parse_state == "normal":
                                            if char == "<":
                                                parse_state = "check_open"
                                                tag_buffer = "<"
                                            else:
                                                full_content_text += char
                                                await self._agent._emit_event(EventType.TOKEN, char, **emit_kwargs)
                                        elif parse_state == "check_open":
                                            tag_buffer += char
                                            if tag_buffer == "<thinking>":
                                                await thinking.start()
                                                parse_state = "thinking"
                                                tag_buffer = ""
                                            elif not "<thinking>".startswith(tag_buffer):
                                                await thinking.end()
                                                full_content_text += tag_buffer
                                                await self._agent._emit_event(EventType.TOKEN, tag_buffer, **emit_kwargs)
                                                parse_state = "normal"
                                                tag_buffer = ""
                                        elif parse_state == "thinking":
                                            if char == "<":
                                                parse_state = "check_close"
                                                tag_buffer = "<"
                                            else:
                                                await thinking.token(char)
                                        elif parse_state == "check_close":
                                            tag_buffer += char
                                            if tag_buffer == "</thinking>":
                                                await thinking.end()
                                                parse_state = "normal"
                                                tag_buffer = ""
                                            elif not "</thinking>".startswith(tag_buffer):
                                                await thinking.token(tag_buffer)
                                                parse_state = "thinking"
                                                tag_buffer = ""
                                elif isinstance(c, ToolRequest):
                                    await thinking.end()
                                    received_tool_requests.append(c)
                finally:
                    await thinking.end()

            if tag_buffer:
                if parse_state in ["check_open", "normal"]:
                    full_content_text += tag_buffer
                    await self._agent._emit_event(EventType.TOKEN, tag_buffer, **emit_kwargs)
                else:
                    await thinking.token(tag_buffer)

            logger.info(
                f"📊 LLM returned: text_len={len(full_content_text)}, tool_requests={len(received_tool_requests)}"
            )

            if received_tool_requests:
                if "tool_requests" not in state.turn_structured_info:
                    state.turn_structured_info["tool_requests"] = []

                for req in received_tool_requests:
                    state.turn_structured_info["tool_requests"].append(req)

                assistant_content = []
                if full_content_text:
                    assistant_content.append(TextContent(text=full_content_text))
                assistant_content.extend(received_tool_requests)
                await self._agent.add_message(
                    state.session_id,
                    Message(role=Role.ASSISTANT, content=assistant_content).only_agent_visible(),
                    state,
                )

            if not received_tool_requests:
                assistant_content = []
                if full_content_text:
                    assistant_content.append(TextContent(text=full_content_text))

                if "tool_responses" not in state.turn_structured_info:
                    state.turn_structured_info["tool_responses"] = []

                if state.turn_structured_info and state.turn_structured_info["tool_responses"]:
                    assistant_content.extend(state.turn_structured_info["tool_responses"])

                await self._agent.add_message(
                    state.session_id,
                    Message(role=Role.ASSISTANT, content=assistant_content),
                    state,
                )
                state.status = AgentStatus.IDLE
                self._agent._schedule_state_save(state.session_id, state)
                break

            exec_results = await self._tool_executor.execute_concurrent(
                received_tool_requests,
                state,
                gen,
                req_ctx,
                run_id=run_id,
                user_id=user_id,
            )

            if state.status == AgentStatus.WAITING_APPROVAL:
                logger.info("Task suspended for approval.")
                return

            if "tool_responses" not in state.turn_structured_info:
                state.turn_structured_info["tool_responses"] = []

            for req, resp in zip(received_tool_requests, exec_results):
                tool_msg = Message.tool_response(resp)
                await self._agent.add_message(state.session_id, tool_msg, state)
                state.turn_structured_info["tool_responses"].append(resp)

            self._agent._schedule_state_save(state.session_id, state)
