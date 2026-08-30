"""
Tests for observability — Milestone 21.
"""

from __future__ import annotations

import json
import time

import pytest

from app.core.observability import AgentTrace, Tracer, get_tracer


def test_agent_trace_defaults():
    t = AgentTrace(user_id="u1", query_preview="What is my tax?")
    assert t.status == "pending"
    assert t.total_input_tokens == 0
    assert t.llm_calls == []
    assert t.tool_calls == []


def test_agent_trace_record_llm_call():
    t = AgentTrace()
    t.record_llm_call("claude-3", "bedrock", 100, 50, 300)
    assert len(t.llm_calls) == 1
    assert t.total_input_tokens == 100
    assert t.total_output_tokens == 50


def test_agent_trace_record_multiple_llm_calls():
    t = AgentTrace()
    t.record_llm_call("model", "bedrock", 100, 50, 200)
    t.record_llm_call("model", "bedrock", 200, 80, 400)
    assert t.total_input_tokens == 300
    assert t.total_output_tokens == 130


def test_agent_trace_record_tool_call():
    t = AgentTrace()
    t.record_tool_call("calculate_tax", True, 50)
    assert len(t.tool_calls) == 1
    assert t.tool_calls[0].name == "calculate_tax"
    assert t.tool_calls[0].success is True


def test_agent_trace_finish():
    t = AgentTrace()
    t.finish("completed")
    assert t.status == "completed"
    assert t.finished_at is not None


def test_agent_trace_latency_ms():
    t = AgentTrace()
    time.sleep(0.01)
    t.finish()
    assert t.latency_ms >= 10


def test_agent_trace_estimated_cost():
    t = AgentTrace()
    t.record_llm_call("model", "bedrock", 1_000_000, 1_000_000, 1000)
    # Input: 1M * $3/M = $3, Output: 1M * $15/M = $15 → total $18
    assert t.estimated_cost_usd == pytest.approx(18.0, abs=0.01)


def test_agent_trace_to_log_dict_safe_keys():
    t = AgentTrace(user_id="u1", query_preview="test query")
    t.record_llm_call("model", "bedrock", 100, 50, 200)
    t.record_tool_call("calculate_tax", True, 30)
    t.finish("completed")

    d = t.to_log_dict()
    # Must have all expected keys
    for key in ["request_id", "trace_id", "user_id", "status", "latency_ms",
                "total_input_tokens", "total_output_tokens", "estimated_cost_usd",
                "tools_called"]:
        assert key in d

    # Must NOT contain secrets
    assert "api_key" not in json.dumps(d)
    assert "password" not in json.dumps(d)


def test_agent_trace_query_truncated():
    long_query = "x" * 200
    t = AgentTrace(query_preview=long_query)
    d = t.to_log_dict()
    assert len(d["query_preview"]) <= 100


def test_agent_trace_tool_success_rate():
    t = AgentTrace()
    t.record_tool_call("calc", True, 10)
    t.record_tool_call("retrieve", False, 20)
    d = t.to_log_dict()
    assert d["tool_success_rate"] == pytest.approx(0.5)


def test_tracer_context_manager_emits(caplog):
    import logging
    tracer = Tracer()
    with caplog.at_level(logging.INFO, logger="app.observability"):
        with tracer.trace(user_id="u1", query="tax question") as trace:
            trace.record_llm_call("model", "bedrock", 50, 20, 100)
            trace.record_tool_call("calculate_tax", True, 30)
            trace.finish("completed")

    # Should have emitted at least one log line
    assert any("request_id" in r.message for r in caplog.records)


def test_tracer_sets_failed_on_exception():
    tracer = Tracer()
    with pytest.raises(RuntimeError):
        with tracer.trace(user_id="u1") as trace:
            raise RuntimeError("something went wrong")

    assert trace.status == "failed"
    assert trace.errors


def test_get_tracer_singleton():
    t1 = get_tracer()
    t2 = get_tracer()
    assert t1 is t2


def test_request_id_middleware():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) == 36  # UUID


def test_request_id_propagated_from_header():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    custom_id = "my-trace-id-12345"
    response = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.headers["x-request-id"] == custom_id
