"""
Agent API endpoint — the primary user-facing route.

POST /api/v1/agent/query
    Accepts a tax question, runs the agent loop, returns a structured response.

Architecture:
    Request
        │
        ▼
    Guardrail pipeline (rate limit → injection check → jurisdiction)
        │
        ▼
    AgentLoop.run() (raw loop) OR LangGraph graph
        │
        ├── LLM calls (Bedrock)
        ├── Tool calls (calculate_tax, calculate_capital_gains, retrieve_tax_rules)
        └── Observations
        │
        ▼
    AgentTrace emitted to CloudWatch
        │
        ▼
    Response with final_answer + citations + usage

This endpoint deliberately uses the raw agent loop (Milestone 8).
The LangGraph endpoint is a separate route (future milestone).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

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
    """Primary agent endpoint."""

    # Get request_id from middleware
    request_id = getattr(http_request.state, "request_id", str(uuid.uuid4()))
    # Placeholder user_id until auth is wired
    user_id = "anonymous"

    logger.info(
        "Agent query received [request_id=%s user_id=%s query_len=%d]",
        request_id, user_id, len(request_body.query),
    )

    # ── Guardrails: input checks ──────────────────────────────────────────────
    warnings: list[str] = []

    try:
        from app.core.config import get_settings
        from app.core.guardrails import GuardrailPipeline

        settings = get_settings()
        pipeline = GuardrailPipeline(daily_limit=settings.daily_request_limit)
        guardrail_result = pipeline.check_input(request_body.query, user_id)

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

    # ── Check LLM is configured ───────────────────────────────────────────────
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

    # ── Build tool registry ───────────────────────────────────────────────────
    from app.tools.registry import ToolRegistry
    from app.tools.tax import CalculateTaxTool
    from app.tools.capital_gains import CalculateCapitalGainsTool

    registry = ToolRegistry()
    registry.register(CalculateTaxTool())
    registry.register(CalculateCapitalGainsTool())

    # Add RAG tool if Qdrant is configured
    try:
        from app.core.config import get_settings
        settings = get_settings()
        if settings.qdrant_url and settings.qdrant_collection:
            from app.rag.qdrant_store import get_qdrant_client
            from app.rag.embeddings import get_embedding_provider
            from app.rag.agentic_rag import AgenticRAGTool

            registry.register(AgenticRAGTool(
                client=get_qdrant_client(),
                collection_name=settings.qdrant_collection,
                embedding_provider=get_embedding_provider(),
            ))
    except Exception as exc:
        logger.warning("RAG tool not available: %s", exc)
        warnings.append("Tax rule retrieval is unavailable (Qdrant not configured).")

    # ── Run agent loop ────────────────────────────────────────────────────────
    from app.core.config import get_settings
    from app.core.observability import get_tracer

    settings = get_settings()
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
            for tc in state.tool_calls:
                trace.record_tool_call(tc.tool_name, tc.success, tc.duration_ms)
            trace.total_input_tokens = state.total_input_tokens
            trace.total_output_tokens = state.total_output_tokens
            trace.finish(state.status)

    except Exception as exc:
        logger.exception("Agent loop failed [request_id=%s]", request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {exc}",
        )

    # ── Output guardrail: PII scan ────────────────────────────────────────────
    if state.final_answer:
        try:
            from app.core.guardrails import check_output_pii
            pii_result = check_output_pii(state.final_answer)
            warnings.extend(pii_result.warnings)
        except Exception:
            pass

    # ── Build response ────────────────────────────────────────────────────────
    from app.core.cost_tracking import build_cost_summary

    cost = build_cost_summary(trace)

    return AgentQueryResponse(
        request_id=request_id,
        status=state.status,
        final_answer=state.final_answer,
        citations=state.citations,
        reasoning=state.reasoning,
        usage=cost.to_dict(),
        warnings=warnings,
    )
