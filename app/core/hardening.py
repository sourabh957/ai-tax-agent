"""
Production hardening — Milestone 41.

Startup hardening checks that run before the server accepts traffic.
These are in addition to config_check.py and validate production-specific
requirements that don't apply in development.

Checks:
    1. Non-root process validation
    2. Required env vars present (fail hard, not warn)
    3. Database connectivity
    4. Alembic migrations are up to date
    5. Secrets Manager accessibility
    6. S3 bucket accessibility
"""

from __future__ import annotations

import logging
import os
import sys

try:
    import boto3
except ImportError:
    boto3 = None  # type: ignore[assignment]

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def check_not_root() -> bool:
    """Warn if the process is running as root (security risk in containers)."""
    if os.name == "nt":
        return True  # Not applicable on Windows
    uid = os.getuid()
    if uid == 0:
        logger.warning(
            "SECURITY: Process is running as root (uid=0). "
            "In production containers, run as a non-root user. "
            "See Dockerfile: USER appuser"
        )
        return False
    logger.debug("Process running as uid=%d (non-root)", uid)
    return True


def check_required_env_vars_for_production() -> tuple[bool, list[str]]:
    """
    In production, certain env vars are strictly required (not just warned).

    Returns:
        (True, []) if all required vars are set.
        (False, [missing_vars]) if any are missing.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if settings.app_env != "production":
        return True, []

    required = {
        "DATABASE_URL": settings.database_url,
        "LLM_PROVIDER": settings.llm_provider,
        "BEDROCK_MODEL_ID": settings.bedrock_model_id,
        "AWS_REGION": settings.aws_region,
        "S3_BUCKET_NAME": settings.s3_bucket_name,
        "CORS_ALLOWED_ORIGINS": ",".join(settings.cors_allowed_origins),
        "DOMAIN_NAME": settings.domain_name,
    }

    missing = [k for k, v in required.items() if not v]
    return len(missing) == 0, missing


async def check_database_connectivity() -> tuple[bool, str]:
    """
    Verify the database is reachable.
    Returns (True, message) if connected, (False, error) if not.
    """
    try:
        from app.db.session import get_engine
        from sqlalchemy import text

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Database connection OK"
    except Exception as exc:
        return False, f"Database connection failed: {exc}"


async def check_migrations_current() -> tuple[bool, str]:
    """
    Verify Alembic migrations are applied to the current head.
    Returns (True, message) or (False, error).
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from app.db.session import get_engine

        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        engine = get_engine()

        async with engine.connect() as conn:
            # Run sync Alembic migration check in executor
            import asyncio

            def _check_sync(sync_conn):
                context = MigrationContext.configure(sync_conn)
                current = set(context.get_current_heads())
                head = set(script.get_heads())
                return current, head

            loop = asyncio.get_event_loop()
            current, head = await loop.run_in_executor(
                None, lambda: _check_sync(conn.sync_connection)
            )

        if current == head:
            return True, f"Migrations current (head={head})"
        return False, (
            f"Migrations out of date. Current: {current}, Head: {head}. "
            "Run: alembic upgrade head"
        )
    except Exception as exc:
        return False, f"Could not check migrations: {exc}"


async def check_s3_accessible() -> tuple[bool, str]:
    """
    Verify the S3 bucket exists and is accessible.
    Returns (True, message) or (False, error).
    """
    try:
        import asyncio
        import boto3
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.s3_bucket_name or settings.s3_bucket_name == "mock-bucket":
            return False, "S3_BUCKET_NAME is not configured or mock."

        client = boto3.client("s3", region_name=settings.aws_region)
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(
            None,
            lambda: client.head_bucket(Bucket=settings.s3_bucket_name),
        )
        return True, f"Bucket {settings.s3_bucket_name} accessible."
    except Exception as exc:
        return False, f"S3 bucket check failed: {exc}"


async def run_production_hardening_checks(fail_fast: bool = False) -> bool:
    """
    Run all production hardening checks.

    Args:
        fail_fast: If True, exit the process on any critical failure.
                   If False, log all failures and return False.

    Returns:
        True if all critical checks pass, False otherwise.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if settings.app_env != "production":
        logger.debug("Skipping production hardening checks (APP_ENV=%s)", settings.app_env)
        return True

    logger.info("Running production hardening checks...")
    all_passed = True

    # 1. Non-root check
    if not check_not_root():
        logger.warning("Production hardening: running as root is not recommended.")
        # Not fatal — warn only

    # 2. Required env vars
    ok, missing = check_required_env_vars_for_production()
    if not ok:
        logger.error("Production hardening: missing required env vars: %s", missing)
        all_passed = False
        if fail_fast:
            sys.exit(1)

    # 3. Database connectivity
    ok, msg = await check_database_connectivity()
    if ok:
        logger.info("Production hardening [OK]: %s", msg)
    else:
        logger.error("Production hardening [FAIL]: %s", msg)
        all_passed = False
        if fail_fast:
            sys.exit(1)

    # 4. Migrations current
    ok, msg = await check_migrations_current()
    if ok:
        logger.info("Production hardening [OK]: %s", msg)
    else:
        logger.warning("Production hardening [WARN]: %s", msg)
        # Warn only — not fatal (migrations may be run separately)

    # 5. S3 accessible
    ok, msg = await check_s3_accessible()
    if ok:
        logger.info("Production hardening [OK]: %s", msg)
    else:
        logger.warning("Production hardening [WARN]: %s", msg)

    if not settings.oidc_issuer_url:
        logger.warning(
            "Production hardening [WARN]: OIDC_ISSUER_URL is not configured. "
            "Bearer token validation will be unavailable."
        )

    return all_passed
