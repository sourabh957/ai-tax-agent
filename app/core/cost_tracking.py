"""
Cost tracking utilities — Milestone 22.

Tracks per-request and aggregate token/cost metrics.
Used by the agent loop to enforce cost controls and by
the observability layer to emit cost data to CloudWatch.

Cost limits:
    MAX_AGENT_ITERATIONS  — limits total LLM calls per request
    MAX_TOOL_CALLS        — limits tool execution per request
    MAX_LLM_CALLS         — hard cap on LLM API calls per request
    DAILY_REQUEST_LIMIT   — limits total requests per user per day

Model pricing (approximate, verify against current AWS/provider pricing):
    These are reference rates only — always check current provider pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Reference pricing per million tokens (USD) — update as pricing changes
PRICING: dict[str, dict[str, float]] = {
    # Claude Sonnet 4.6 on Bedrock
    "anthropic.claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    # Claude Haiku on Bedrock
    "anthropic.claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    # Default fallback
    "default": {"input": 3.00, "output": 15.00},
}


@dataclass
class RequestCostSummary:
    """Cost summary for a single agent request."""
    model_id: str
    input_tokens: int
    output_tokens: int
    llm_call_count: int
    tool_call_count: int
    iteration_count: int
    latency_ms: int
    estimated_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "iteration_count": self.iteration_count,
            "latency_ms": self.latency_ms,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Estimate request cost in USD based on token usage.

    Uses the PRICING lookup table; falls back to 'default' if model not found.
    Always verify against current provider pricing before relying on these numbers.

    Args:
        model_id:      The Bedrock/provider model ID.
        input_tokens:  Total input tokens consumed.
        output_tokens: Total output tokens generated.

    Returns:
        Estimated cost in USD.
    """
    pricing = PRICING.get(model_id) or PRICING["default"]
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


def build_cost_summary(agent_trace) -> RequestCostSummary:
    """
    Build a RequestCostSummary from a completed AgentTrace.

    Args:
        agent_trace: A completed app.core.observability.AgentTrace instance.

    Returns:
        RequestCostSummary with full cost breakdown.
    """
    model_id = (
        agent_trace.llm_calls[0].model
        if agent_trace.llm_calls
        else "default"
    )
    cost = estimate_cost(
        model_id,
        agent_trace.total_input_tokens,
        agent_trace.total_output_tokens,
    )
    return RequestCostSummary(
        model_id=model_id,
        input_tokens=agent_trace.total_input_tokens,
        output_tokens=agent_trace.total_output_tokens,
        llm_call_count=len(agent_trace.llm_calls),
        tool_call_count=len(agent_trace.tool_calls),
        iteration_count=agent_trace.iteration_count,
        latency_ms=agent_trace.latency_ms,
        estimated_cost_usd=cost,
    )
