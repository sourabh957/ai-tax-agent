"""
Tests for Milestones 25 + 26 + 27:
    - LangGraph graph structure and state
    - LangGraph node logic (mocked LLM and tools)
    - Production Docker configuration checks
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.langgraph_agent import (
    TaxAgentState,
    build_should_continue,
    build_tools_node,
)


# ============================================================
# TaxAgentState
# ============================================================

def test_tax_agent_state_is_typed_dict():
    """TaxAgentState must be a TypedDict with all required keys."""
    import typing
    hints = typing.get_type_hints(TaxAgentState)
    for key in ["messages", "tool_call_count", "iteration_count", "user_id"]:
        assert key in hints


# ============================================================
# should_continue edge
# ============================================================

def make_state(
    messages=None,
    iterations=0,
    tool_calls=0,
) -> TaxAgentState:
    return {
        "messages": messages or [],
        "iteration_count": iterations,
        "tool_call_count": tool_calls,
        "user_id": "u1",
        "request_id": "req-1",
        "final_answer": "",
    }


def make_ai_message(content="answer", tool_calls=None):
    from langchain_core.messages import AIMessage
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


def test_should_continue_no_tool_calls_returns_end():
    fn = build_should_continue()
    state = make_state(messages=[make_ai_message("Your tax is ₹44,200.")])
    assert fn(state) == "end"


def test_should_continue_with_tool_calls_returns_tools():
    fn = build_should_continue()
    msg = make_ai_message()
    msg.tool_calls = [{"name": "calculate_tax", "args": {"gross_income": 1000000}, "id": "tc1"}]
    state = make_state(messages=[msg])
    assert fn(state) == "tools"


def test_should_continue_max_iterations_returns_end():
    fn = build_should_continue(max_iterations=3)
    msg = make_ai_message()
    msg.tool_calls = [{"name": "calculate_tax", "args": {}, "id": "tc1"}]
    state = make_state(messages=[msg], iterations=3)
    assert fn(state) == "end"


def test_should_continue_max_tool_calls_returns_end():
    fn = build_should_continue(max_tool_calls=5)
    msg = make_ai_message()
    msg.tool_calls = [{"name": "calculate_tax", "args": {}, "id": "tc1"}]
    state = make_state(messages=[msg], tool_calls=5)
    assert fn(state) == "end"


def test_should_continue_empty_messages_returns_end():
    fn = build_should_continue()
    state = make_state(messages=[])
    assert fn(state) == "end"


# ============================================================
# tools_node
# ============================================================

@pytest.mark.asyncio
async def test_tools_node_executes_tool_and_returns_tool_message():
    from langchain_core.messages import AIMessage, ToolMessage

    # Mock registry
    registry = MagicMock()
    result_mock = MagicMock()
    result_mock.success = True
    result_mock.data = {"total_tax": 44200}
    registry.execute = AsyncMock(return_value=result_mock)

    tools_fn = build_tools_node(registry)

    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = [
        {"name": "calculate_tax", "args": {"gross_income": 1000000}, "id": "tc-1"}
    ]

    state = make_state(messages=[ai_msg])
    result = await tools_fn(state)

    assert "messages" in result
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)
    assert result["tool_call_count"] == 1


@pytest.mark.asyncio
async def test_tools_node_handles_tool_failure():
    from langchain_core.messages import AIMessage, ToolMessage

    registry = MagicMock()
    fail_result = MagicMock()
    fail_result.success = False
    fail_result.error = "Tool failed: invalid year"
    registry.execute = AsyncMock(return_value=fail_result)

    tools_fn = build_tools_node(registry)

    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = [
        {"name": "calculate_tax", "args": {"gross_income": 100}, "id": "tc-2"}
    ]

    state = make_state(messages=[ai_msg])
    result = await tools_fn(state)

    tool_msg = result["messages"][0]
    assert "Error" in tool_msg.content


@pytest.mark.asyncio
async def test_tools_node_no_tool_calls_returns_empty():
    from langchain_core.messages import AIMessage

    registry = MagicMock()
    tools_fn = build_tools_node(registry)

    ai_msg = AIMessage(content="Final answer")
    # no tool_calls attribute
    state = make_state(messages=[ai_msg])
    result = await tools_fn(state)

    assert result["messages"] == []
    assert result["tool_call_count"] == 0


# ============================================================
# Graph compilation (structure test — no LLM calls)
# ============================================================

def test_graph_compiles_without_error():
    """Graph should compile without needing real AWS credentials."""
    from langgraph.graph import END, START, StateGraph

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
        content="answer", tool_calls=[]
    ))

    mock_registry = MagicMock()

    should_continue = build_should_continue()
    agent_node = MagicMock()
    tools_fn = build_tools_node(mock_registry)

    graph = StateGraph(TaxAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_fn)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")

    compiled = graph.compile()
    assert compiled is not None


# ============================================================
# Dockerfile checks (M27)
# ============================================================

def test_dockerfile_has_multi_stage_build():
    with open("Dockerfile") as f:
        content = f.read()
    assert "AS builder" in content
    assert "AS production" in content


def test_dockerfile_non_root_user():
    with open("Dockerfile") as f:
        content = f.read()
    assert "useradd" in content
    assert "USER appuser" in content


def test_dockerfile_has_healthcheck():
    with open("Dockerfile") as f:
        content = f.read()
    assert "HEALTHCHECK" in content
    assert "/api/v1/health" in content


def test_dockerfile_runs_config_check():
    with open("Dockerfile") as f:
        content = f.read()
    assert "config_check" in content


def test_dockerignore_excludes_env():
    with open(".dockerignore") as f:
        content = f.read()
    assert ".env" in content


def test_dockerignore_excludes_venv():
    with open(".dockerignore") as f:
        content = f.read()
    assert ".venv" in content or "venv/" in content


def test_dockerignore_excludes_tests():
    with open(".dockerignore") as f:
        content = f.read()
    assert "tests/" in content
