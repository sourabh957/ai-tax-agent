"""
Pydantic schemas shared across all LLM providers.

The rest of the application uses these types — never provider-specific types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


class UsageInfo(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    """Unified response from any LLM provider."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: UsageInfo = Field(default_factory=UsageInfo)
    model: str = ""
    finish_reason: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def is_final_answer(self) -> bool:
        return not self.has_tool_calls and self.content is not None


class ToolDefinition(BaseModel):
    """Schema for a tool exposed to the LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]
