"""
Agent loop integration tests.

Tests the full agent loop with various scenarios:
    - Multi-tool call sequences
    - Guardrail integration
    - Observability trace integration
    - Error recovery
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.schemas import LLMResponse, UsageInfo


def _final(answer: str) -> LLMResponse:
    return LLMResponse(
        content=json.dumps({"type": "final_answer", "answer": answer,
                            "reasoning": "r", "citations": ["IT Act"]}),
        usage=UsageInfo(input_tokens=50, output_tokens=20),
    )


def _tool(name: str, args: dict) -> LLMResponse:
    return LLMResponse(
        content=json.dumps({"type": "tool_call", "tool_name": name,
                            "arguments": args, "reasoning": "need tool"}),
        usage=UsageInfo(input_tokens=40, output_tokens=20),
    )


@pytest.mark.asyncio
async def test_agent_multi_tool_sequence():
    """Agent calls two tools in sequence then answers."""
    from app.agents.loop import AgentLoop
    from app.llm.client import LLMClient
    from app.llm.base import LLMProvider
    from app.tools.registry import ToolRegistry
    from app.tools.tax import CalculateTaxTool
    from app.tools.capital_gains import CalculateCapitalGainsTool
    from app.llm.schemas import Message
    from collections.abc import AsyncGenerator

    responses = [
        _tool("calculate_tax", {"gross_income": 1_000_000, "regime": "new"}),
        _tool("calculate_capital_gains", {
            "transactions": [{"asset_class": "equity", "buy_date": "2023-01-01",
                              "sell_date": "2024-06-01", "buy_price": 100_000, "sell_price": 200_000}],
            "financial_year": "2024-25",
        }),
        _final("Your income tax is ₹44,200 and equity LTCG tax is ₹0 (within exemption)."),
    ]
    idx = [0]

    class MockProvider(LLMProvider):
        @property
        def provider_name(self): return "mock"
        @property
        def model_id(self): return "mock"
        async def generate(self, messages, **kwargs):
            r = responses[idx[0]]; idx[0] += 1; return r
        async def generate_structured(self, messages, output_schema, **kwargs): return output_schema()
        async def stream(self, messages, **kwargs) -> AsyncGenerator[str, None]:
            async def _g(): yield "ok"
            return _g()

    from app.llm.client import LLMClient
    client = LLMClient(MockProvider())

    registry = ToolRegistry()
    registry.register(CalculateTaxTool())
    registry.register(CalculateCapitalGainsTool())

    with patch("app.agents.loop.get_settings") as ms:
        ms.return_value = MagicMock(max_agent_iterations=8, max_tool_calls=10,
                                    max_llm_calls=6, daily_request_limit=100)
        loop = AgentLoop(client, registry)
        state = await loop.run("Calculate tax and LTCG for my portfolio", user_id="u1")

    assert state.status == "completed"
    assert state.tool_call_count == 2
    assert state.tool_calls[0].tool_name == "calculate_tax"
    assert state.tool_calls[1].tool_name == "calculate_capital_gains"
    assert state.tool_calls[0].success is True
    assert state.tool_calls[1].success is True


@pytest.mark.asyncio
async def test_agent_observability_trace_populated():
    """AgentTrace should be populated after a run."""
    from app.agents.loop import AgentLoop
    from app.llm.client import LLMClient
    from app.llm.base import LLMProvider
    from app.tools.registry import ToolRegistry
    from app.tools.tax import CalculateTaxTool
    from app.core.observability import AgentTrace
    from collections.abc import AsyncGenerator

    class MockProvider(LLMProvider):
        @property
        def provider_name(self): return "mock"
        @property
        def model_id(self): return "mock"
        async def generate(self, messages, **kwargs): return _final("Tax is ₹44,200")
        async def generate_structured(self, messages, output_schema, **kwargs): return output_schema()
        async def stream(self, messages, **kwargs) -> AsyncGenerator[str, None]:
            async def _g(): yield "ok"
            return _g()

    client = LLMClient(MockProvider())
    registry = ToolRegistry()
    registry.register(CalculateTaxTool())

    with patch("app.agents.loop.get_settings") as ms:
        ms.return_value = MagicMock(max_agent_iterations=8, max_tool_calls=10,
                                    max_llm_calls=6, daily_request_limit=100)
        loop = AgentLoop(client, registry)
        state = await loop.run("What is my tax?", user_id="u1")

    # Build a trace from state (as the agent route does)
    from app.core.observability import AgentTrace
    trace = AgentTrace(user_id="u1", query_preview="What is my tax?")
    trace.iteration_count = state.iteration_count
    trace.total_input_tokens = state.total_input_tokens
    trace.total_output_tokens = state.total_output_tokens
    trace.finish(state.status)

    assert trace.status == "completed"
    assert trace.latency_ms >= 0
    d = trace.to_log_dict()
    assert d["status"] == "completed"
