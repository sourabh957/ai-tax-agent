"""
Tool Registry — central registry for all agent tools.

Usage:
    registry = ToolRegistry()
    registry.register(CalculateTaxTool())
    registry.register(GetUserProfileTool())

    tool = registry.get("calculate_tax")
    result = await tool.execute(validated_input, user_id=user_id)

    # Get all tool definitions for the LLM
    definitions = registry.get_tool_definitions()

Architecture:
    The LLM only knows about tools via ToolDefinition schemas.
    It cannot execute tools directly — it requests them by name.
    The registry validates the name exists before execution.
"""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry that maps tool names to BaseTool instances.

    - Tools are registered at startup.
    - The agent loop calls get() to retrieve a tool by name.
    - The LLM never receives tool implementations — only ToolDefinition schemas.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if a tool with the same name already exists."""
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                "Use a unique name for each tool."
            )
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool:
        """
        Retrieve a tool by name.

        Raises:
            KeyError: If no tool with this name is registered.
        """
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' is not registered. "
                f"Available tools: {sorted(self._tools.keys())}"
            )
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_tool_definitions(self):
        """Return ToolDefinition list suitable for passing to the LLM."""
        return [tool.to_tool_definition() for tool in self._tools.values()]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_id: str,
    ) -> ToolResult:
        """
        Validate and execute a tool requested by the LLM.

        Flow:
            1. Look up tool by name (raises if unknown)
            2. Validate arguments via Pydantic (raises ValidationError if invalid)
            3. Execute and return ToolResult

        Never raises on tool execution errors — they are captured in ToolResult.
        """
        tool = self.get(tool_name)  # may raise KeyError

        from pydantic import ValidationError

        try:
            validated_input = tool.validate_input(arguments)
        except ValidationError as exc:
            logger.warning(
                "Tool input validation failed [tool=%s]: %s", tool_name, exc
            )
            return ToolResult.fail(
                f"Invalid arguments for tool '{tool_name}': {exc}"
            )

        try:
            result = await tool.execute(validated_input, user_id=user_id)
        except Exception as exc:
            logger.exception("Tool execution error [tool=%s]", tool_name)
            return ToolResult.fail(
                f"Tool '{tool_name}' raised an unexpected error: {exc}"
            )

        return result
