"""
Observability — Milestone 21.

Every agent execution is tracked with:
    - request_id  (set by middleware, propagated through the call stack)
    - trace_id    (same as request_id, available for future distributed tracing)
    - model, provider, latency, token usage
    - retrieval calls, tool calls, iterations
    - errors

Structured JSON logs are emitted to stdout so CloudWatch Logs Insights
can query them with: { $.request_id = "..." }

Design:
    - No secrets or financial PII are logged (PANs, passwords, raw documents)
    - Token usage is logged for cost tracking
    - Latency is broken down per phase (embed, retrieve, rerank, llm, total)

Usage:
    from app.core.observability import get_tracer, AgentTrace

    tracer = get_tracer()
    with tracer.trace(request_id=..., user_id=...) as t:
        t.record_llm_call(model=..., input_tokens=..., output_tokens=..., latency_ms=...)
        t.record_tool_call(name=..., success=..., latency_ms=...)
    # trace is emitted as structured JSON on exit
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger("app.observability")


# ---------------------------------------------------------------------------
# Per-request trace
# ---------------------------------------------------------------------------

@dataclass
class LLMCallRecord:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    error: str | None = None


@dataclass
class ToolCallRecord:
    name: str
    success: bool
    latency_ms: int
    error: str | None = None


@dataclass
class AgentTrace:
    """
    Collects all observability data for a single agent run.

    Created at request start, emitted as structured JSON at request end.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    user_id: str = ""
    query_preview: str = ""         # first 100 chars of the query (no PII)
    status: str = "pending"

    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    iteration_count: int = 0

    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = self.request_id

    def record_llm_call(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        error: str | None = None,
    ) -> None:
        self.llm_calls.append(LLMCallRecord(
            model=model, provider=provider,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=latency_ms, error=error,
        ))
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def record_tool_call(
        self,
        name: str,
        success: bool,
        latency_ms: int,
        error: str | None = None,
    ) -> None:
        self.tool_calls.append(ToolCallRecord(
            name=name, success=success, latency_ms=latency_ms, error=error
        ))

    def record_error(self, error: str) -> None:
        self.errors.append(error)

    def finish(self, status: str = "completed") -> None:
        self.status = status
        self.finished_at = time.time()

    @property
    def latency_ms(self) -> int:
        end = self.finished_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def estimated_cost_usd(self) -> float:
        """
        Rough cost estimate using Claude Sonnet 4.6 pricing as reference.
        Always check current pricing — this is an approximation.

        Pricing reference (2024):
            Claude Sonnet: ~$3/M input tokens, ~$15/M output tokens
        """
        input_cost = (self.total_input_tokens / 1_000_000) * 3.00
        output_cost = (self.total_output_tokens / 1_000_000) * 15.00
        return round(input_cost + output_cost, 6)

    def to_log_dict(self) -> dict[str, Any]:
        """
        Structured log payload — safe to emit to CloudWatch.

        NEVER includes: API keys, passwords, PAN, Aadhaar, raw document content.
        """
        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "query_preview": self.query_preview[:100],
            "status": self.status,
            "latency_ms": self.latency_ms,
            "iteration_count": self.iteration_count,
            "llm_call_count": len(self.llm_calls),
            "tool_call_count": len(self.tool_calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "errors": self.errors,
            "tools_called": [tc.name for tc in self.tool_calls],
            "tool_success_rate": (
                sum(1 for tc in self.tool_calls if tc.success) / len(self.tool_calls)
                if self.tool_calls else 1.0
            ),
        }

    def emit(self) -> None:
        """Emit the trace as a single structured JSON log line."""
        logger.info(json.dumps(self.to_log_dict()))


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class Tracer:
    """Manages AgentTrace lifecycle."""

    @contextmanager
    def trace(
        self,
        request_id: str | None = None,
        user_id: str = "",
        query: str = "",
    ) -> Generator[AgentTrace, None, None]:
        """
        Context manager that creates a trace, yields it, then emits on exit.

        Usage:
            with tracer.trace(request_id=..., user_id=..., query=...) as t:
                t.record_llm_call(...)
                t.record_tool_call(...)
        """
        trace = AgentTrace(
            request_id=request_id or str(uuid.uuid4()),
            user_id=user_id,
            query_preview=query[:100],
            status="running",
        )
        try:
            yield trace
        except Exception as exc:
            trace.record_error(str(exc))
            trace.finish("failed")
            raise
        finally:
            if trace.finished_at is None:
                trace.finish("completed")
            trace.emit()


_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer
