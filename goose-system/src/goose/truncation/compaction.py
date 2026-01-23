"""
Message Compaction

Message compaction via LLM summarization.
Reference: goose-rs/crates/goose/src/context_mgmt/mod.rs
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from .token_counter import TokenCounter, create_token_counter


logger = logging.getLogger(__name__)

DEFAULT_COMPACTION_THRESHOLD = 0.8

CONVERSATION_CONTINUATION_TEXT = """The previous message contains a summary that was prepared because a context limit was reached.
Do not mention that you read a summary or that conversation summarization occurred.
Just continue the conversation naturally based on the summarized context."""

TOOL_LOOP_CONTINUATION_TEXT = """The previous message contains a summary that was prepared because a context limit was reached.
Do not mention that you read a summary or that conversation summarization occurred.
Continue calling tools as necessary to complete the task."""

MANUAL_COMPACT_CONTINUATION_TEXT = """The previous message contains a summary that was prepared at the user's request.
Do not mention that you read a summary or that conversation summarization occurred.
Just continue the conversation naturally based on the summarized context."""


@dataclass
class CompactionConfig:
    """Compaction configuration"""
    threshold: float = DEFAULT_COMPACTION_THRESHOLD
    manual_compact: bool = False
    keep_recent_messages: int = 5


@dataclass
class CompactionResult:
    """Result of message compaction"""
    original_message_count: int
    compacted_message_count: int
    tokens_saved: int
    summary: str
    success: bool
    error: Optional[str] = None


class MessageCompactor:
    """
    Message compactor that summarizes old messages.
    
    Features:
    - LLM-based summarization
    - Progressive tool response removal
    - Visibility metadata management
    """
    
    def __init__(
        self,
        provider: Any,
        token_counter: Optional[TokenCounter] = None,
        config: Optional[CompactionConfig] = None,
    ):
        self.provider = provider
        self.token_counter = token_counter or create_token_counter()
        self.config = config or CompactionConfig()
    
    def check_if_compaction_needed(
        self,
        conversation_messages: List[Dict[str, Any]],
        context_limit: int,
        current_token_count: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if compaction is needed based on context usage
        
        Returns:
            Tuple of (needs_compaction, usage_info)
        """
        if self.config.threshold <= 0.0 or self.config.threshold >= 1.0:
            return False, {"reason": "Compaction disabled by threshold"}
        
        if current_token_count is None:
            messages_text = self._messages_to_text(conversation_messages)
            current_token_count = self.token_counter.count_text_tokens(messages_text)
        
        usage_ratio = current_token_count / context_limit
        needs_compaction = usage_ratio > self.config.threshold
        
        usage_info = {
            "current_tokens": current_token_count,
            "context_limit": context_limit,
            "usage_percent": round(usage_ratio * 100, 2),
            "threshold_percent": round(self.config.threshold * 100, 2),
            "needs_compaction": needs_compaction,
        }
        
        logger.info(
            f"Compaction check: {current_token_count}/{context_limit} "
            f"({usage_ratio*100:.1f}%), threshold: {self.config.threshold*100:.1f}%, "
            f"needs: {needs_compaction}"
        )
        
        return needs_compaction, usage_info
    
    async def compact_messages(
        self,
        conversation_messages: List[Dict[str, Any]],
        system_prompt: str,
        is_manual: bool = False,
    ) -> CompactionResult:
        """
        Compact messages by summarizing
        
        Args:
            conversation_messages: Current conversation messages
            system_prompt: System prompt
            is_manual: If True, this is a user-initiated compaction
            
        Returns:
            CompactionResult with summary and metadata
        """
        original_count = len(conversation_messages)
        
        if original_count <= self.config.keep_recent_messages:
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=original_count,
                tokens_saved=0,
                summary="No compaction needed (message count below threshold)",
                success=True,
            )
        
        try:
            # Extract text content from messages
            messages_for_summarization = self._prepare_messages_for_summary(
                conversation_messages
            )
            
            # Generate summary using LLM
            summary = await self._generate_summary(
                system_prompt,
                messages_for_summarization,
                is_manual,
            )
            
            # Create compacted conversation
            compacted = self._create_compacted_conversation(
                conversation_messages,
                summary,
                is_manual,
            )
            
            # Calculate token savings
            original_text = self._messages_to_text(conversation_messages)
            compacted_text = self._messages_to_text(compacted)
            tokens_saved = (
                self.token_counter.count_text_tokens(original_text) -
                self.token_counter.count_text_tokens(compacted_text)
            )
            
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=len(compacted),
                tokens_saved=max(0, tokens_saved),
                summary=summary,
                success=True,
            )
            
        except Exception as e:
            logger.exception(f"Compaction failed: {e}")
            return CompactionResult(
                original_message_count=original_count,
                compacted_message_count=original_count,
                tokens_saved=0,
                summary="",
                success=False,
                error=str(e),
            )
    
    def _prepare_messages_for_summary(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Prepare messages for summarization (extract text content)"""
        prepared = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Handle content as list
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")
                        if block_type == "text":
                            text_parts.append(block.get("text", ""))
                        elif block_type == "tool_use":
                            tool_name = block.get("name", "unknown")
                            input_text = str(block.get("input", {}))
                            text_parts.append(f"[TOOL: {tool_name}] {input_text}")
                        elif block_type == "tool_result":
                            text_parts.append(f"[TOOL RESULT] {block.get('content', '')}")
                    else:
                        text_parts.append(str(content))
                content = "\n".join(text_parts)
            
            # Truncate very long messages
            if len(content) > 2000:
                content = content[:2000] + "..."
            
            prepared.append({
                "role": role,
                "content": content,
            })
        
        return prepared
    
    async def _generate_summary(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        is_manual: bool,
    ) -> str:
        """Generate summary using LLM"""
        # Build summarization prompt
        messages_text = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in messages
        )
        
        prompt = f"""{system_prompt}

The following is a conversation history that needs to be summarized due to context limits:

{messages_text}

Please provide a concise summary of the key points, decisions, and current state of the conversation. Focus on:
1. What the user asked for
2. What actions have been taken
3. What the current status is
4. Any important context for continuing

Summary:"""
        
        try:
            response, _ = await self.provider.agenerate(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
            )
            
            if hasattr(response, 'text'):
                return response.text
            elif isinstance(response, dict):
                return response.get("content", str(response))
            else:
                return str(response)
                
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}")
            # Fallback to simple truncation summary
            return self._simple_fallback_summary(messages)
    
    def _simple_fallback_summary(self, messages: List[Dict[str, str]]) -> str:
        """Simple fallback summary when LLM fails"""
        if not messages:
            return "No conversation history."
        
        # Extract key info
        user_messages = [m for m in messages if m.get("role") == "user"]
        tool_uses = sum(1 for m in messages if "[TOOL:" in m.get("content", ""))
        
        return f"Conversation with {len(user_messages)} user messages and {tool_uses} tool calls."
    
    def _create_compacted_conversation(
        self,
        original_messages: List[Dict[str, Any]],
        summary: str,
        is_manual: bool,
    ) -> List[Dict[str, Any]]:
        """
        Create compacted conversation with summary
        """
        keep_count = self.config.keep_recent_messages
        recent_messages = original_messages[-keep_count:]
        
        # Determine continuation text
        if is_manual:
            continuation = MANUAL_COMPACT_CONTINUATION_TEXT
        else:
            continuation = CONVERSATION_CONTINUATION_TEXT
        
        # Build compacted conversation
        compacted = []
        
        # Add summary message (visible to assistant only)
        compacted.append({
            "role": "user",
            "content": f"[SUMMARY]\n{summary}\n[/SUMMARY]",
            "metadata": {
                "agent_visible": True,
                "user_visible": False,
                "is_summary": True,
            }
        })
        
        # Add continuation message
        compacted.append({
            "role": "assistant",
            "content": continuation,
            "metadata": {
                "agent_visible": True,
                "user_visible": False,
                "is_continuation": True,
            }
        })
        
        # Add recent messages (preserve last N messages)
        for msg in recent_messages:
            # Mark old messages as invisible to agent
            if "metadata" in msg:
                msg["metadata"] = dict(msg["metadata"])
                msg["metadata"]["agent_visible"] = False
            else:
                msg["metadata"] = {"agent_visible": False}
            compacted.append(msg)
        
        return compacted
    
    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to single text for token counting"""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        text_parts.append(str(block.get("text", block)))
                    else:
                        text_parts.append(str(content))
                content = "\n".join(text_parts)
            
            parts.append(f"[{role}]: {content}")
        
        return "\n".join(parts)
    
    def filter_tool_responses(
        self,
        messages: List[Dict[str, Any]],
        remove_percent: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Filter out some tool responses from the middle (progressive removal)
        
        Args:
            messages: List of messages
            remove_percent: Percentage of tool responses to remove (0-100)
            
        Returns:
            Filtered messages
        """
        if remove_percent == 0:
            return messages
        
        # Find tool response indices
        tool_indices = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            tool_indices.append(i)
                            break
        
        if not tool_indices:
            return messages
        
        # Calculate how many to remove
        num_to_remove = max(1, (len(tool_indices) * remove_percent) // 100)
        
        # Remove from middle (middle-out strategy)
        middle = len(tool_indices) // 2
        indices_to_remove = []
        
        for i in range(num_to_remove):
            if i % 2 == 0:
                offset = i // 2
                if middle > offset:
                    indices_to_remove.append(tool_indices[middle - offset - 1])
            else:
                offset = i // 2
                if middle + offset < len(tool_indices):
                    indices_to_remove.append(tool_indices[middle + offset])
        
        # Filter out removed messages
        return [
            msg for i, msg in enumerate(messages)
            if i not in indices_to_remove
        ]


def format_message_for_compacting(msg: Dict[str, Any]) -> str:
    """Format a single message for compaction"""
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "text")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    name = block.get("name", "unknown")
                    input_data = block.get("input", {})
                    text_parts.append(f"[TOOL: {name}] {input_data}")
                elif block_type == "tool_result":
                    text_parts.append(f"[TOOL RESULT] {block.get('content', '')}")
            else:
                text_parts.append(str(content))
        content = "\n".join(text_parts)
    
    return f"[{role}]: {content}"


def create_compactor(
    provider: Any,
    threshold: float = DEFAULT_COMPACTION_THRESHOLD,
) -> MessageCompactor:
    """Create a compactor with the given provider"""
    config = CompactionConfig(threshold=threshold)
    return MessageCompactor(provider, config=config)
