"""
AI Tax Agent — FastAPI application entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, documents
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
        # Log the failure but do NOT prevent startup — missing optional
        # services (Qdrant, DB) are acceptable in development.
        # A hard exit here would break local development that only uses Bedrock.
        logger.warning(
            "Configuration check reported errors. "
            "Some features may be unavailable."
        )

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tightened per-environment in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])

    return app


app = create_app()
