"""
AI Tax Agent — FastAPI application entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RequestIDMiddleware
from app.api.routes import agent, auth, conversations, documents, financial_years, health, usage
from app.core.config import get_settings
from app.core.config_check import run_checks
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup validation before the server accepts traffic."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger("app.startup")
    logger.info(
        "Starting AI Tax Agent [version=%s env=%s llm_provider=%s]",
        app.version,
        settings.app_env,
        settings.llm_provider or "unconfigured",
    )

    ok = run_checks()
    if not ok:
        logger.warning(
            "Configuration check reported errors. "
            "Some features may be unavailable."
        )

    try:
        from app.core.hardening import run_production_hardening_checks

        await run_production_hardening_checks(fail_fast=False)
    except Exception as exc:
        logger.warning("Production hardening checks failed: %s", exc)

    yield

    logger.info("AI Tax Agent shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()
    app_version = "0.1.0"

    app = FastAPI(
        title="AI Tax Agent",
        description=(
            "Production AI Tax Agent — LLM reasoning + RAG + "
            "deterministic tax engine on AWS."
        ),
        version=app_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)

    allowed_origins = settings.cors_allowed_origins or (
        ["http://localhost:3000"] if settings.app_env == "development" else []
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_app_version_header(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-App-Version"] = app.version
        return response

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(usage.router, prefix="/api/v1", tags=["usage"])
    app.include_router(agent.router, prefix="/api/v1", tags=["agent"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
    app.include_router(financial_years.router, prefix="/api/v1", tags=["financial-years"])

    return app


app = create_app()
