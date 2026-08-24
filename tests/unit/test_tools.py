"""
Unit tests for the tool registry and base tool.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.tools.base import BaseTool, ToolResult
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Test tool fixture
# ---------------------------------------------------------------------------


class EchoInput(BaseModel):
    message: str


class EchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes the input message back."

    @property
    def input_schema(self) -> type[BaseModel]:
        return EchoInput

    async def execute(self, validated_input: EchoInput, *, user_id: str) -> ToolResult:
        return ToolResult.ok({"echoed": validated_input.message})


class FailingTool(BaseTool):
    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "Always fails."

    @property
    def input_schema(self) -> type[BaseModel]:
        return EchoInput

    async def execute(self, validated_input: EchoInput, *, user_id: str) -> ToolResult:
        raise RuntimeError("intentional error")


# ---------------------------------------------------------------------------
# ToolResult tests
# ---------------------------------------------------------------------------


def test_tool_result_ok():
    r = ToolResult.ok({"value": 42})
    assert r.success is True
    assert r.data == {"value": 42}
    assert r.error is None


def test_tool_result_fail():
    r = ToolResult.fail("something went wrong")
    assert r.success is False
    assert r.error == "something went wrong"
    assert r.data is None


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(EchoTool())
    tool = reg.get("echo")
    assert tool.name == "echo"


def test_duplicate_registration_raises():
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoTool())


def test_get_unknown_tool_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get("nonexistent")


def test_has_tool():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert reg.has("echo") is True
    assert reg.has("unknown") is False


def test_tool_names():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert "echo" in reg.tool_names


def test_get_tool_definitions():
    reg = ToolRegistry()
    reg.register(EchoTool())
    defs = reg.get_tool_definitions()
    assert len(defs) == 1
    assert defs[0].name == "echo"


@pytest.mark.asyncio
async def test_execute_valid_tool():
    reg = ToolRegistry()
    reg.register(EchoTool())
    result = await reg.execute("echo", {"message": "hello"}, user_id="user-1")
    assert result.success is True
    assert result.data["echoed"] == "hello"


@pytest.mark.asyncio
async def test_execute_invalid_arguments_returns_failure():
    reg = ToolRegistry()
    reg.register(EchoTool())
    result = await reg.execute("echo", {"wrong_field": 123}, user_id="user-1")
    assert result.success is False
    assert "Invalid arguments" in result.error


@pytest.mark.asyncio
async def test_execute_unknown_tool_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        await reg.execute("nonexistent", {}, user_id="user-1")


@pytest.mark.asyncio
async def test_execute_tool_exception_returns_failure():
    reg = ToolRegistry()
    reg.register(FailingTool())
    result = await reg.execute("failing_tool", {"message": "hi"}, user_id="user-1")
    assert result.success is False
    assert "unexpected error" in result.error
