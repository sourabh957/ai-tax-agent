"""
AI Tax Agent — FastAPI application entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, documents, usage, agent
from app.api.middleware import RequestIDMiddleware
from app.core.config import get_settings
from app.core.config_check import run_checks
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup validation before the server accepts traffic."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger("app.startup")
    logger.info("Starting AI Tax Agent [env=%s]", settings.app_env)

    ok = run_checks()
    if not ok:
        logger.warning(
            "Configuration check reported errors. "
            "Some features may be unavailable."
        )

    # Production hardening (only runs when APP_ENV=production)
    try:
        from app.core.hardening import run_production_hardening_checks
        await run_production_hardening_checks(fail_fast=False)
    except Exception as exc:
        logger.warning("Production hardening checks failed: %s", exc)

    yield

    logger.info("AI Tax Agent shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Tax Agent",
        description=(
            "Production AI Tax Agent — LLM reasoning + RAG + "
            "deterministic tax engine on AWS."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)
    # CORS — tighten origins in production (see docs/production_config.md)
    allowed_origins = (
        ["*"]
        if settings.app_env != "production"
        else []  # Set explicit origins via CORS_ALLOWED_ORIGINS env var in prod
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(usage.router, prefix="/api/v1", tags=["usage"])
    app.include_router(agent.router, prefix="/api/v1", tags=["agent"])

    return app


app = create_app()
