"""
Health and readiness endpoints.

GET /api/v1/health   — liveness probe (is the process running?)
GET /api/v1/ready    — readiness probe (is configuration valid?)
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()

# Record process start time for uptime reporting
_START_TIME = time.time()


@router.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe — returns 200 if the process is alive."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
    }


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness probe — checks whether required configuration is present.

    Returns 200 if ready, 503 if critical configuration is missing.
    For ECS/ALB health checks and Kubernetes readiness probes.
    """
    from fastapi import Response
    from fastapi.responses import JSONResponse

    settings = get_settings()
    checks: dict[str, str] = {}
    is_ready = True

    # LLM provider
    if settings.llm_provider:
        checks["llm_provider"] = "configured"
        if settings.llm_provider == "bedrock":
            if settings.bedrock_model_id and settings.aws_region:
                checks["bedrock"] = "configured"
            else:
                checks["bedrock"] = "missing BEDROCK_MODEL_ID or AWS_REGION"
                is_ready = False
    else:
        checks["llm_provider"] = "not configured"
        is_ready = False

    # Database
    checks["database"] = "configured" if settings.database_url else "not configured"

    # Qdrant
    checks["qdrant"] = "configured" if settings.qdrant_url else "not configured"

    body = {
        "status": "ready" if is_ready else "not ready",
        "environment": settings.app_env,
        "checks": checks,
    }

    status_code = 200 if is_ready else 503
    return JSONResponse(content=body, status_code=status_code)
