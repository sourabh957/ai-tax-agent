"""
Rate limiting API route — exposes per-user usage stats.

GET /api/v1/usage
    Returns current daily usage count and limit for the requesting user.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.guardrails import get_rate_limiter
from app.core.config import get_settings

router = APIRouter()


class UsageResponse(BaseModel):
    user_id: str
    requests_today: int
    daily_limit: int
    requests_remaining: int


@router.get("/usage", response_model=UsageResponse)
async def get_usage() -> UsageResponse:
    """
    Return daily usage stats for the current user.

    TODO: Replace anonymous user_id with real auth once auth is wired.
    """
    user_id = "anonymous"
    settings = get_settings()
    limiter = get_rate_limiter()

    count = limiter.get_count(user_id)
    limit = settings.daily_request_limit

    return UsageResponse(
        user_id=user_id,
        requests_today=count,
        daily_limit=limit,
        requests_remaining=max(0, limit - count),
    )
