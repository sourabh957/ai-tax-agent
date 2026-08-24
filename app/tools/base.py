"""
Base Tool class.

Every tool in the agent's tool registry must extend BaseTool.

Architecture:
    LLM requests a tool by name + arguments
        │
        ▼
    ToolRegistry.get(name) → BaseTool
        │
        ▼
    tool.validate_input(arguments) → validated Pydantic model
        │
        ▼
    tool.execute(validated_input, user_id) → output
        │
        ▼
    Observation added to agent state
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Standardised output returned by every tool."""

    success: bool
    data: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, error=error)


class BaseTool(ABC):
    """
    Abstract base class for all agent tools.

    Subclasses must define:
        - name (str)
        - description (str)
        - input_schema (Pydantic BaseModel subclass)
        - execute()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name used by the LLM to request this tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human/LLM-readable description of what the tool does."""

    @property
    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """Pydantic model that defines and validates the tool's input."""

    def validate_input(self, arguments: dict[str, Any]) -> BaseModel:
        """
        Validate raw LLM-supplied arguments against the input schema.

        Raises:
            pydantic.ValidationError: If arguments are invalid.
        """
        return self.input_schema.model_validate(arguments)

    @abstractmethod
    async def execute(
        self,
        validated_input: BaseModel,
        *,
        user_id: str,
    ) -> ToolResult:
        """
        Execute the tool with validated inputs.

        Args:
            validated_input: Already-validated Pydantic instance.
            user_id: The requesting user — for authorization checks.

        Returns:
            ToolResult with success/failure and data.
        """

    def to_tool_definition(self):
        """Convert to LLMProvider ToolDefinition for the converse API."""
        from app.llm.schemas import ToolDefinition

        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema.model_json_schema(),
        )
