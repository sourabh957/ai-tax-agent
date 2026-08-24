"""
Agent decision schemas — structured outputs that drive the agent loop.

The LLM must output one of these structured decisions at each step.
Pydantic validates the output before any action is taken.

Architecture:
    LLM output (JSON)
        │
        ▼
    AgentDecision (Pydantic validation)
        │
        ├── FinalAnswer → return to user
        └── ToolCallDecision → execute tool → observe → next iteration
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DecisionType(str, Enum):
    FINAL_ANSWER = "final_answer"
    TOOL_CALL = "tool_call"


class FinalAnswer(BaseModel):
    """The agent has enough information to answer the user."""

    type: Literal[DecisionType.FINAL_ANSWER] = DecisionType.FINAL_ANSWER
    answer: str = Field(..., min_length=1, description="The answer to return to the user.")
    reasoning: str = Field(
        default="",
        description="Brief explanation of how the answer was derived.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Source references used to construct the answer.",
    )


class ToolCallDecision(BaseModel):
    """The agent needs to call a tool before it can answer."""

    type: Literal[DecisionType.TOOL_CALL] = DecisionType.TOOL_CALL
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = Field(
        default="",
        description="Why this tool is needed at this step.",
    )

    @field_validator("tool_name")
    @classmethod
    def tool_name_no_spaces(cls, v: str) -> str:
        if " " in v.strip():
            raise ValueError("tool_name must not contain spaces.")
        return v.strip()


# Discriminated union — Pydantic uses the 'type' field to pick the right model
AgentDecision = FinalAnswer | ToolCallDecision


def parse_agent_decision(data: dict[str, Any]) -> AgentDecision:
    """
    Parse a raw dict (e.g. parsed LLM JSON output) into an AgentDecision.

    Raises:
        ValueError: If the data does not match either decision schema.
    """
    from pydantic import TypeAdapter

    adapter = TypeAdapter(AgentDecision)
    return adapter.validate_python(data)
