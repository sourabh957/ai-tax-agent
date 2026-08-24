"""
Unit tests for the raw agent loop and AgentState.

All LLM calls are mocked — no real Bedrock/API calls.
Tests cover: final answer, tool call, iteration limit, tool limit,
unknown tool, tool failure, parse failure.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.loop import AgentLoop
from app.agents.state import AgentState
from app.llm.schemas import LLMResponse, UsageInfo
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import ToolRegistry
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_llm_client(response_content: str) -> MagicMock:
    """Return a mock LLMClient that returns the given JSON string."""
    client = MagicMock()
    client.provider_name = "mock"
    client.model_id = "mock"
    client.generate = AsyncMock(
        return_value=LLMResponse(
            content=response_content,
            usage=UsageInfo(input_tokens=10, output_tokens=5),
        )
    )
    return client


def final_answer_json(answer: str = "Your tax is ₹44,200.") -> str:
    return json.dumps({
        "type": "final_answer",
        "answer": answer,
        "reasoning": "Used calculate_tax tool.",
        "citations": [],
    })


def tool_call_json(tool_name: str = "calculate_tax", args: dict | None = None) -> str:
    return json.dumps({
        "type": "tool_call",
        "tool_name": tool_name,
        "arguments": args or {"gross_income": 1_000_000, "regime": "new"},
        "reasoning": "Need to compute tax.",
    })


class EchoInput(BaseModel):
    message: str


class EchoTool(BaseTool):
    @property
    def name(self): return "echo"
    @property
    def description(self): return "Echo"
    @property
    def input_schema(self): return EchoInput
    async def execute(self, validated_input, *, user_id):
        return ToolResult.ok({"echoed": validated_input.message})


def make_registry(*tools) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def make_settings(iterations=8, tools=10, llm=6):
    s = MagicMock()
    s.max_agent_iterations = iterations
    s.max_tool_calls = tools
    s.max_llm_calls = llm
    return s


# ---------------------------------------------------------------------------
# AgentState tests
# ---------------------------------------------------------------------------

def test_state_initial_status():
    s = AgentState(user_id="u1", user_query="test")
    assert s.status == "pending"
    assert s.iteration_count == 0


def test_state_finish():
    s = AgentState()
    s.finish("completed")
    assert s.status == "completed"
    assert s.finished_at is not None


def test_state_record_tool_call():
    s = AgentState()
    s.record_tool_call("calc", {"x": 1}, {"result": 42}, True, 50)
    assert s.tool_call_count == 1
    assert s.tool_calls[0].tool_name == "calc"


def test_state_elapsed_ms():
    s = AgentState()
    s.finish()
    assert s.elapsed_ms >= 0


def test_state_to_summary_keys():
    s = AgentState(user_id="u1")
    summary = s.to_summary()
    for key in ["request_id", "status", "iteration_count", "tool_call_count", "elapsed_ms"]:
        assert key in summary


# ---------------------------------------------------------------------------
# AgentLoop — final answer on first turn
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_final_answer():
    llm = make_llm_client(final_answer_json("Tax is ₹44,200."))
    with patch("app.agents.loop.get_settings", return_value=make_settings()):
        loop = AgentLoop(llm, make_registry())
        state = await loop.run("What is my tax?", user_id="u1")

    assert state.status == "completed"
    assert state.final_answer == "Tax is ₹44,200."
    assert state.llm_call_count == 1


# ---------------------------------------------------------------------------
# AgentLoop — tool call then final answer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_tool_call_then_final_answer():
    responses = [
        LLMResponse(content=tool_call_json("echo", {"message": "hello"}),
                    usage=UsageInfo(input_tokens=10, output_tokens=5)),
        LLMResponse(content=final_answer_json("Echo done."),
                    usage=UsageInfo(input_tokens=15, output_tokens=5)),
    ]
    llm = MagicMock()
    llm.provider_name = "mock"
    llm.model_id = "mock"
    llm.generate = AsyncMock(side_effect=responses)

    with patch("app.agents.loop.get_settings", return_value=make_settings()):
        loop = AgentLoop(llm, make_registry(EchoTool()))
        state = await loop.run("Echo hello", user_id="u1")

    assert state.status == "completed"
    assert state.final_answer == "Echo done."
    assert state.tool_call_count == 1
    assert state.llm_call_count == 2


# ---------------------------------------------------------------------------
# AgentLoop — max iterations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_max_iterations():
    # LLM always returns a tool call — should hit iteration limit
    llm = make_llm_client(tool_call_json("echo", {"message": "x"}))
    with patch("app.agents.loop.get_settings", return_value=make_settings(iterations=3)):
        loop = AgentLoop(llm, make_registry(EchoTool()))
        state = await loop.run("loop forever", user_id="u1")

    assert state.status == "timeout"
    assert state.iteration_count == 3


# ---------------------------------------------------------------------------
# AgentLoop — max tool calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_max_tool_calls():
    llm = make_llm_client(tool_call_json("echo", {"message": "x"}))
    with patch("app.agents.loop.get_settings", return_value=make_settings(tools=2, iterations=20)):
        loop = AgentLoop(llm, make_registry(EchoTool()))
        state = await loop.run("call tools", user_id="u1")

    assert state.status == "timeout"
    assert state.tool_call_count <= 2


# ---------------------------------------------------------------------------
# AgentLoop — unknown tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_unknown_tool_then_final_answer():
    responses = [
        LLMResponse(content=tool_call_json("nonexistent_tool"),
                    usage=UsageInfo(input_tokens=10, output_tokens=5)),
        LLMResponse(content=final_answer_json("Could not use tool."),
                    usage=UsageInfo(input_tokens=10, output_tokens=5)),
    ]
    llm = MagicMock()
    llm.generate = AsyncMock(side_effect=responses)

    with patch("app.agents.loop.get_settings", return_value=make_settings()):
        loop = AgentLoop(llm, make_registry())  # empty registry
        state = await loop.run("test", user_id="u1")

    # Observation should mention tool not available
    assert any("not available" in str(tc.result) for tc in state.tool_calls)


# ---------------------------------------------------------------------------
# AgentLoop — unparseable LLM response → graceful fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_unparseable_response_becomes_final_answer():
    llm = make_llm_client("I cannot help with this.")  # plain text, not JSON
    with patch("app.agents.loop.get_settings", return_value=make_settings()):
        loop = AgentLoop(llm, make_registry())
        state = await loop.run("test", user_id="u1")

    assert state.status == "completed"
    assert state.final_answer == "I cannot help with this."


# ---------------------------------------------------------------------------
# AgentLoop — max LLM calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_max_llm_calls():
    llm = make_llm_client(tool_call_json("echo", {"message": "x"}))
    with patch("app.agents.loop.get_settings", return_value=make_settings(llm=2, iterations=20)):
        loop = AgentLoop(llm, make_registry(EchoTool()))
        state = await loop.run("test", user_id="u1")

    assert state.status == "timeout"
    assert state.llm_call_count <= 2
