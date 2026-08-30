"""
Tests for Milestones 22 + 23 + 24:
    - Rate limiting + cost controls
    - LangChain tool wrappers (mocked — no real Bedrock)
    - LangChain provider factory
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cost_tracking import (
    RequestCostSummary,
    build_cost_summary,
    estimate_cost,
)
from app.core.observability import AgentTrace


# ============================================================
# Milestone 22 — Cost Tracking
# ============================================================

def test_estimate_cost_known_model():
    cost = estimate_cost("anthropic.claude-sonnet-4-6", 1_000_000, 1_000_000)
    # $3 input + $15 output = $18
    assert cost == pytest.approx(18.0, abs=0.01)


def test_estimate_cost_default_fallback():
    cost = estimate_cost("unknown-model-xyz", 0, 0)
    assert cost == 0.0


def test_estimate_cost_zero_tokens():
    assert estimate_cost("anthropic.claude-haiku-4-5", 0, 0) == 0.0


def test_estimate_cost_output_heavier():
    """Output tokens cost more than input tokens."""
    cost_input_heavy = estimate_cost("anthropic.claude-sonnet-4-6", 1_000_000, 0)
    cost_output_heavy = estimate_cost("anthropic.claude-sonnet-4-6", 0, 1_000_000)
    assert cost_output_heavy > cost_input_heavy


def test_build_cost_summary_from_trace():
    trace = AgentTrace(user_id="u1")
    trace.record_llm_call("anthropic.claude-sonnet-4-6", "bedrock", 500, 200, 300)
    trace.record_llm_call("anthropic.claude-sonnet-4-6", "bedrock", 300, 100, 200)
    trace.record_tool_call("calculate_tax", True, 50)
    trace.iteration_count = 2
    trace.finish("completed")

    summary = build_cost_summary(trace)
    assert isinstance(summary, RequestCostSummary)
    assert summary.input_tokens == 800
    assert summary.output_tokens == 300
    assert summary.llm_call_count == 2
    assert summary.tool_call_count == 1
    assert summary.iteration_count == 2
    assert summary.estimated_cost_usd > 0


def test_cost_summary_to_dict():
    trace = AgentTrace()
    trace.record_llm_call("anthropic.claude-sonnet-4-6", "bedrock", 100, 50, 200)
    trace.finish()
    d = build_cost_summary(trace).to_dict()
    for key in ["model_id", "input_tokens", "output_tokens", "total_tokens",
                "llm_call_count", "estimated_cost_usd"]:
        assert key in d


def test_usage_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/usage")
    assert response.status_code == 200
    body = response.json()
    assert "requests_today" in body
    assert "daily_limit" in body
    assert "requests_remaining" in body


# ============================================================
# Milestone 24 — LangChain Tool Wrappers
# ============================================================

def test_lc_calculate_tax_tool_direct():
    """LangChain tax tool wraps our existing CalculateTaxTool."""
    from app.llm.langchain_tools import make_lc_calculate_tax_tool

    lc_tool = make_lc_calculate_tax_tool(user_id="u1")
    # Direct invoke (bypasses LangChain agent machinery)
    result = lc_tool.invoke({
        "gross_income": 1_000_000,
        "regime": "new",
        "financial_year": "2024-25",
    })
    assert isinstance(result, dict)
    # new regime result may have total_tax or recommended_regime depending on mode
    assert "total_tax" in result or "new_regime" in result


def test_lc_calculate_tax_compare_mode():
    from app.llm.langchain_tools import make_lc_calculate_tax_tool

    lc_tool = make_lc_calculate_tax_tool(user_id="u1")
    result = lc_tool.invoke({"gross_income": 1_500_000, "regime": "compare"})
    assert "recommended_regime" in result
    assert "new_regime" in result
    assert "old_regime" in result


def test_lc_calculate_capital_gains_tool():
    from app.llm.langchain_tools import make_lc_calculate_capital_gains_tool

    lc_tool = make_lc_calculate_capital_gains_tool(user_id="u1")
    txns = [
        {
            "asset_class": "equity",
            "buy_date": "2023-01-01",
            "sell_date": "2024-06-01",
            "buy_price": 100000,
            "sell_price": 200000,
        }
    ]
    result = lc_tool.invoke({
        "transactions_json": json.dumps(txns),
        "financial_year": "2024-25",
    })
    assert "equity_ltcg_gross" in result
    assert result["equity_ltcg_gross"] == 100_000


def test_lc_capital_gains_invalid_json():
    from app.llm.langchain_tools import make_lc_calculate_capital_gains_tool

    lc_tool = make_lc_calculate_capital_gains_tool(user_id="u1")
    with pytest.raises(ValueError, match="valid JSON"):
        lc_tool.invoke({"transactions_json": "not json"})


def test_get_all_lc_tools_returns_list():
    from app.llm.langchain_tools import get_all_lc_tools

    tools = get_all_lc_tools(user_id="u1")
    assert len(tools) >= 2
    names = [t.name for t in tools]
    assert "lc_calculate_tax" in names
    assert "lc_calculate_capital_gains" in names


# ============================================================
# LangChain provider factory
# ============================================================

def test_get_llm_client_langchain_bedrock_provider():
    """Factory should resolve langchain_bedrock as a valid provider name."""
    from app.llm.client import get_llm_client, _build_provider

    # Verify the provider name routes correctly without instantiating
    get_llm_client.cache_clear()
    with patch("app.llm.client.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(llm_provider="unknown_xyz")
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            get_llm_client()

    # Verify langchain_bedrock is a known provider (no ValueError)
    with patch("app.llm.client.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(llm_provider="langchain_bedrock")
        with patch("app.llm.providers.langchain_bedrock.LangChainBedrockProvider") as mock_cls:
            mock_cls.return_value = MagicMock(provider_name="langchain_bedrock", model_id="m")
            client = get_llm_client()
            assert client.provider_name == "langchain_bedrock"

    get_llm_client.cache_clear()


def test_langchain_bedrock_provider_name():
    """Provider name should be 'langchain_bedrock'."""
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            aws_region="ap-south-1",
        )
        with patch("langchain_aws.ChatBedrock"):
            from app.llm.providers.langchain_bedrock import LangChainBedrockProvider
            provider = LangChainBedrockProvider.__new__(LangChainBedrockProvider)
            provider._model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
            provider._region = "ap-south-1"
            assert provider.provider_name == "langchain_bedrock"
