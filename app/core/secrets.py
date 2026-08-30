"""
AWS Secrets Manager integration — Milestone 34.

In production (ECS), secrets are stored in Secrets Manager and injected
into the container as environment variables via the ECS task definition
`secrets` field. The application reads them as normal env vars.

This module provides:
    1. Direct secret fetching for cases where Secrets Manager is used as
       the runtime source (e.g. multi-value JSON secrets like DB credentials)
    2. A helper to build DATABASE_URL from a stored JSON secret
    3. Validation that secrets exist and are accessible

Architecture:
    Development:
        .env file → os.environ → app/core/config.py → Settings

    Production (ECS):
        Secrets Manager → ECS task definition secrets injection → os.environ
        → app/core/config.py → Settings
        (The application code is identical — only the injection path differs)

    Direct fetch (for complex secrets):
        Secrets Manager → get_secret() → parse JSON → Settings

Why we don't fetch all secrets via boto3 at startup:
    - ECS secrets injection is more secure (no boto3 call needed in app code)
    - AWS manages rotation and access logging automatically
    - The app works identically in dev (.env) and prod (Secrets Manager)

This module is used ONLY when:
    - Building DATABASE_URL from a multi-field JSON secret
    - Validating secret accessibility at startup
    - Rotating secrets programmatically
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class SecretsManagerClient:
    """
    Thin wrapper around boto3 Secrets Manager.

    Uses the standard AWS credential chain:
        - IAM task role (ECS production)
        - AWS CLI profile (local development)
        - Environment variables (CI)

    Never requires hardcoded credentials.
    """

    def __init__(self, region: str) -> None:
        self._region = region
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    "secretsmanager",
                    region_name=self._region,
                )
            except ImportError:
                raise RuntimeError("boto3 is not installed. Run: pip install boto3")
        return self._client

    def get_secret_string(self, secret_id: str) -> str:
        """
        Fetch the string value of a secret.

        Args:
            secret_id: The secret name or ARN.

        Returns:
            The secret string value.

        Raises:
            RuntimeError: If the secret cannot be fetched.
        """
        try:
            client = self._get_client()
            response = client.get_secret_value(SecretId=secret_id)
            secret = response.get("SecretString") or ""
            logger.debug("Fetched secret: %s", secret_id)
            return secret
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch secret '{secret_id}' from Secrets Manager: {exc}"
            ) from exc

    def get_secret_json(self, secret_id: str) -> dict[str, Any]:
        """
        Fetch and parse a JSON secret.

        Returns:
            Parsed dict of secret key-value pairs.
        """
        raw = self.get_secret_string(secret_id)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Secret '{secret_id}' is not valid JSON: {exc}"
            ) from exc

    def secret_exists(self, secret_id: str) -> bool:
        """Return True if the secret exists and is accessible."""
        try:
            self.get_secret_string(secret_id)
            return True
        except Exception:
            return False


@lru_cache(maxsize=1)
def get_secrets_client() -> SecretsManagerClient:
    """Return the singleton Secrets Manager client."""
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.aws_region:
        raise RuntimeError(
            "AWS_REGION is required to use Secrets Manager. Set it in .env."
        )
    return SecretsManagerClient(region=settings.aws_region)


def build_database_url_from_secret(secret_id: str, region: str) -> str:
    """
    Build a PostgreSQL DATABASE_URL from a Secrets Manager JSON secret.

    Expected secret JSON format:
    {
        "username": "...",
        "password": "...",
        "host": "...",
        "port": "5432",
        "dbname": "tax_agent"
    }

    Returns:
        A postgresql+asyncpg:// URL for SQLAlchemy.

    Usage (in app startup when DB credentials are in Secrets Manager):
        url = build_database_url_from_secret(
            "ai-tax-agent-dev/db-credentials",
            "ap-south-1",
        )
    """
    client = SecretsManagerClient(region=region)
    data = client.get_secret_json(secret_id)

    required = ["username", "password", "host", "dbname"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(
            f"Secret '{secret_id}' is missing required fields: {missing}"
        )

    port = data.get("port", "5432")
    return (
        f"postgresql+asyncpg://{data['username']}:{data['password']}"
        f"@{data['host']}:{port}/{data['dbname']}"
    )


def validate_secret_access(secret_id: str, region: str) -> bool:
    """
    Validate that a secret is accessible.

    Used in startup checks to fail fast if Secrets Manager access is broken.

    Returns:
        True if accessible, False otherwise (does not raise).
    """
    try:
        client = SecretsManagerClient(region=region)
        return client.secret_exists(secret_id)
    except Exception as exc:
        logger.warning("Secret access validation failed: %s", exc)
        return False
