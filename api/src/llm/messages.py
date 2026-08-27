"""Provider-neutral LLM message models and normalization helpers."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["system", "user", "assistant"]


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    thought_signature: bytes | None = None


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


class ChatMessage(BaseModel):
    role: MessageRole
    content: list[ContentBlock]


def normalize_messages(messages: list[dict[Any, Any]]) -> list[ChatMessage]:
    normalized: list[ChatMessage] = []
    for message in messages:
        role = _normalize_role(message.get("role"))
        content = message.get("content", "")
        blocks = normalize_content_blocks(content)
        if blocks:
            normalized.append(ChatMessage(role=role, content=blocks))
    return normalized


def split_system_messages(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    system_chunks: list[str] = []
    conversation: list[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            text = content_text(message.content).strip()
            if text:
                system_chunks.append(text)
        else:
            conversation.append(message)
    return "\n\n".join(system_chunks) or None, conversation


def normalize_content_blocks(content: Any) -> list[ContentBlock]:
    if isinstance(content, str):
        return [TextBlock(text=content)]
    if isinstance(content, list):
        return [_normalize_content_block(block) for block in content]
    return [_normalize_content_block(content)]


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, TextBlock):
                chunks.append(item.text)
            elif isinstance(item, ToolResultBlock):
                chunks.append(item.content)
            elif isinstance(item, ToolUseBlock):
                chunks.append(json.dumps({"name": item.name, "input": item.input}, ensure_ascii=True))
            elif isinstance(item, dict) and "text" in item:
                chunks.append(str(item["text"]))
            else:
                chunks.append(json.dumps(_json_safe(item), ensure_ascii=True))
        return "\n".join(chunks)
    return json.dumps(_json_safe(content), ensure_ascii=True)


def _normalize_content_block(block: Any) -> ContentBlock:
    if isinstance(block, TextBlock | ToolUseBlock | ToolResultBlock):
        return block
    if not isinstance(block, dict):
        return TextBlock(text=str(block))

    block_type = block.get("type")
    if block_type == "text":
        return TextBlock(text=str(block.get("text", "")))
    if block_type == "tool_use":
        return ToolUseBlock(
            id=str(block.get("id") or block.get("tool_use_id") or ""),
            name=str(block.get("name") or ""),
            input=block.get("input") if isinstance(block.get("input"), dict) else {},
            thought_signature=_thought_signature(block),
        )
    if block_type == "tool_result":
        return ToolResultBlock(
            tool_use_id=str(block.get("tool_use_id") or block.get("toolUseId") or block.get("id") or ""),
            content=content_text(block.get("content", "")),
        )

    if "text" in block:
        return TextBlock(text=str(block["text"]))

    tool_use = block.get("toolUse")
    if isinstance(tool_use, dict):
        return ToolUseBlock(
            id=str(tool_use.get("toolUseId") or tool_use.get("id") or ""),
            name=str(tool_use.get("name") or ""),
            input=tool_use.get("input") if isinstance(tool_use.get("input"), dict) else {},
            thought_signature=_thought_signature(tool_use),
        )

    tool_result = block.get("toolResult")
    if isinstance(tool_result, dict):
        return ToolResultBlock(
            tool_use_id=str(tool_result.get("toolUseId") or tool_result.get("id") or ""),
            content=content_text(tool_result.get("content", "")),
        )

    return TextBlock(text=json.dumps(_json_safe(block), ensure_ascii=True))


def _normalize_role(role: Any) -> MessageRole:
    if role in {"system", "user", "assistant"}:
        return role
    return "user"


def _thought_signature(block: dict[str, Any]) -> bytes | None:
    value = block.get("thoughtSignature") or block.get("thought_signature")
    return value if isinstance(value, bytes) else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
