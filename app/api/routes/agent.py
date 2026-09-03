"""
Agent API endpoints.

POST /api/v1/agent/query
    Accepts a tax question, runs the agent loop, returns a structured response.

POST /api/v1/agent/stream
    Returns the same response over Server-Sent Events (SSE).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class AgentQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The tax question to ask the agent.",
        examples=["What is my tax liability under new regime for ₹12L salary in FY 2024-25?"],
    )
    financial_year: str = Field(
        default="2024-25",
        description="Financial year context, e.g. '2024-25'.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for multi-turn tracking.",
    )


class AgentQueryResponse(BaseModel):
    request_id: str
    status: str
    final_answer: str | None
    citations: list[str]
    reasoning: str
    usage: dict[str, Any]
    warnings: list[str]


@dataclass
class AgentExecutionResult:
    response: AgentQueryResponse


def _chunk_text(text: str) -> list[str]:
    if not text:
        return []

    chunks: list[str] = []
    words = text.split()
    for index, word in enumerate(words):
        suffix = " " if index < len(words) - 1 else ""
        chunks.append(f"{word}{suffix}")
    return chunks or [text]


def _format_sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def _get_request_id(http_request: Request) -> str:
    return getattr(http_request.state, "request_id", str(uuid.uuid4()))


async def _run_guardrails(query: str, user_id: str) -> list[str]:
    warnings: list[str] = []
    try:
        from app.core.config import get_settings
        from app.core.guardrails import GuardrailPipeline

        settings = get_settings()
        pipeline = GuardrailPipeline(daily_limit=settings.daily_request_limit)
        guardrail_result = pipeline.check_input(query, user_id)

        if not guardrail_result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS
                if "limit" in guardrail_result.reason.lower()
                else status.HTTP_400_BAD_REQUEST,
                detail=guardrail_result.reason,
            )
        warnings.extend(guardrail_result.warnings)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Guardrail check failed: %s", exc)

    return warnings


def _build_tool_registry(warnings: list[str]):
    from app.core.config import get_settings
    from app.tools.capital_gains import CalculateCapitalGainsTool
    from app.tools.registry import ToolRegistry
    from app.tools.tax import CalculateTaxTool

    settings = get_settings()
    registry = ToolRegistry()
    registry.register(CalculateTaxTool())
    registry.register(CalculateCapitalGainsTool())

    try:
        if settings.qdrant_url and settings.qdrant_collection:
            from app.rag.agentic_rag import AgenticRAGTool
            from app.rag.embeddings import get_embedding_provider
            from app.rag.qdrant_store import get_qdrant_client

            registry.register(
                AgenticRAGTool(
                    client=get_qdrant_client(),
                    collection_name=settings.qdrant_collection,
                    embedding_provider=get_embedding_provider(),
                )
            )
    except Exception as exc:
        logger.warning("RAG tool not available: %s", exc)
        warnings.append("Tax rule retrieval is unavailable (Qdrant not configured).")

    return registry


async def _execute_agent_query(
    request_body: AgentQueryRequest,
    http_request: Request,
) -> AgentExecutionResult:
    request_id = _get_request_id(http_request)
    user_id = "anonymous"

    logger.info(
        "Agent query received [request_id=%s user_id=%s query_len=%d]",
        request_id, user_id, len(request_body.query),
    )

    warnings = await _run_guardrails(request_body.query, user_id)

    try:
        from app.llm.client import get_llm_client

        llm_client = get_llm_client()
    except RuntimeError as exc:
        logger.error("LLM not configured: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The AI agent is not available. "
                "LLM provider is not configured. "
                "Set LLM_PROVIDER and BEDROCK_MODEL_ID in the environment."
            ),
        )

    registry = _build_tool_registry(warnings)

    from app.core.cost_tracking import build_cost_summary
    from app.core.observability import get_tracer

    tracer = get_tracer()

    try:
        async with tracer.trace(
            request_id=request_id,
            user_id=user_id,
            query=request_body.query,
        ) as trace:
            from app.agents.loop import AgentLoop

            agent = AgentLoop(llm_client, registry)
            state = await agent.run(
                user_query=request_body.query,
                user_id=user_id,
                session_id=request_body.session_id or request_id,
            )

            trace.iteration_count = state.iteration_count
            for tool_call in state.tool_calls:
                trace.record_tool_call(
                    tool_call.tool_name,
                    tool_call.success,
                    tool_call.duration_ms,
                )
            trace.total_input_tokens = state.total_input_tokens
            trace.total_output_tokens = state.total_output_tokens
            trace.finish(state.status)

            cost = build_cost_summary(trace)
    except Exception as exc:
        logger.exception("Agent loop failed [request_id=%s]", request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {exc}",
        )

    if state.final_answer:
        try:
            from app.core.guardrails import check_output_pii

            pii_result = check_output_pii(state.final_answer)
            warnings.extend(pii_result.warnings)
        except Exception:
            pass

    response = AgentQueryResponse(
        request_id=request_id,
        status=state.status,
        final_answer=state.final_answer,
        citations=state.citations,
        reasoning=state.reasoning,
        usage=cost.to_dict(),
        warnings=warnings,
    )
    return AgentExecutionResult(response=response)


@router.post(
    "/agent/query",
    response_model=AgentQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask the AI Tax Agent a question",
    description=(
        "Submit a tax question to the AI Tax Agent. "
        "The agent will reason, call tools (tax engine, RAG), and return a structured answer with citations. "
        "Subject to daily rate limits."
    ),
)
async def agent_query(
    request_body: AgentQueryRequest,
    http_request: Request,
) -> AgentQueryResponse:
    result = await _execute_agent_query(request_body, http_request)
    return result.response


async def _stream_agent_result(
    response: AgentQueryResponse,
) -> AsyncGenerator[str, None]:
    for chunk in _chunk_text(response.final_answer or ""):
        payload = json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)
        yield _format_sse(payload)
        await asyncio.sleep(0)

    done_payload = json.dumps(
        {
            "type": "done",
            "final_answer": response.final_answer,
            "citations": response.citations,
            "usage": response.usage,
            "warnings": response.warnings,
            "request_id": response.request_id,
            "status": response.status,
            "reasoning": response.reasoning,
        },
        ensure_ascii=False,
    )
    yield _format_sse(done_payload)
    yield _format_sse("[DONE]")


@router.post(
    "/agent/stream",
    status_code=status.HTTP_200_OK,
    summary="Ask the AI Tax Agent with SSE streaming",
)
async def agent_query_stream(
    request_body: AgentQueryRequest,
    http_request: Request,
) -> StreamingResponse:
    result = await _execute_agent_query(request_body, http_request)
    return StreamingResponse(
        _stream_agent_result(result.response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
