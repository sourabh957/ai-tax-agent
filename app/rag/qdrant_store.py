"""
Qdrant client factory.

Provides a single QdrantClient instance configured from environment variables.
Never hardcodes URLs, API keys, or collection names.

Local dev:   QDRANT_URL=http://localhost:6333  (docker-compose)
Production:  QDRANT_URL=https://<cluster>.qdrant.io  QDRANT_API_KEY=<key>
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_qdrant_client():
    """
    Return the configured QdrantClient singleton.

    Raises:
        RuntimeError: If QDRANT_URL is not set.
    """
    settings = get_settings()

    if not settings.qdrant_url:
        raise RuntimeError(
            "QDRANT_URL is not configured. "
            "Set it in .env (e.g. QDRANT_URL=http://localhost:6333)."
        )

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        raise RuntimeError(
            "qdrant-client is not installed. "
            "Run: pip install qdrant-client"
        )

    kwargs: dict = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key

    logger.info("Connecting to Qdrant at %s", settings.qdrant_url)
    return QdrantClient(**kwargs)
