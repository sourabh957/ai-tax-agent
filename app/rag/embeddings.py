"""
Embedding provider abstraction.

The rest of the RAG pipeline depends on EmbeddingProvider — never on a
specific library directly. This makes it easy to swap:

    Local dev   → SentenceTransformers (free, runs offline)
    Production  → Amazon Bedrock Titan Embeddings (or another Bedrock model)

Configuration:
    EMBEDDING_PROVIDER=local          (default — sentence-transformers)
    EMBEDDING_PROVIDER=bedrock
    EMBEDDING_MODEL=...               (model name/ID)
    EMBEDDING_DIMENSION=384           (must match the Qdrant collection)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache

logger = logging.getLogger(__name__)

# Default local model — small, fast, good quality for semantic search
DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"   # 384 dimensions
DEFAULT_DIMENSION = 384


class EmbeddingProvider(ABC):
    """Abstract embedding interface."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a float vector."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. More efficient than calling embed() in a loop."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension — must match the Qdrant collection configuration."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier."""


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.

    Runs fully offline — no API calls, no cost.
    Used for local development and unit tests.

    Default model: all-MiniLM-L6-v2 (384 dims, ~80MB download on first use)
    """

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # lazy load

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading SentenceTransformer model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model

    async def embed(self, text: str) -> list[float]:
        import asyncio
        model = self._load()
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None, lambda: model.encode(text, normalize_embeddings=True).tolist()
        )
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        model = self._load()
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(
            None, lambda: model.encode(texts, normalize_embeddings=True).tolist()
        )
        return vectors

    @property
    def dimension(self) -> int:
        # Avoid loading the model just to return the dimension
        _known = {
            "all-MiniLM-L6-v2": 384,
            "all-MiniLM-L12-v2": 384,
            "all-mpnet-base-v2": 768,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
        }
        return _known.get(self._model_name, DEFAULT_DIMENSION)

    @property
    def model_name(self) -> str:
        return self._model_name


class BedrockEmbeddingProvider(EmbeddingProvider):
    """
    Amazon Bedrock Titan Embeddings provider.

    Uses the standard AWS credential chain — no hardcoded keys.
    Suitable for production / ECS deployments.

    Default model: amazon.titan-embed-text-v2:0  (1536 dims)
    """

    DEFAULT_BEDROCK_MODEL = "amazon.titan-embed-text-v2:0"
    DEFAULT_BEDROCK_DIM = 1536

    def __init__(self, model_id: str | None = None, region: str | None = None) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        self._model_id = model_id or self.DEFAULT_BEDROCK_MODEL
        self._region = region or settings.aws_region
        if not self._region:
            raise RuntimeError("AWS_REGION is required for Bedrock embeddings.")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        import json as _json
        client = self._get_client()
        loop = asyncio.get_event_loop()

        async def _embed_one(t: str) -> list[float]:
            body = _json.dumps({"inputText": t})
            raw = await loop.run_in_executor(
                None,
                lambda: client.invoke_model(
                    modelId=self._model_id,
                    body=body,
                    contentType="application/json",
                    accept="application/json",
                ),
            )
            result = _json.loads(raw["body"].read())
            return result["embedding"]

        return [await _embed_one(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self.DEFAULT_BEDROCK_DIM

    @property
    def model_name(self) -> str:
        return self._model_id


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """
    Return the configured embedding provider singleton.

    Reads EMBEDDING_PROVIDER from settings (defaults to 'local').
    """
    from app.core.config import get_settings
    settings = get_settings()

    # Read optional embedding config (not yet in Settings — graceful fallback)
    provider_name = getattr(settings, "embedding_provider", "local") or "local"

    if provider_name == "bedrock":
        model = getattr(settings, "embedding_model", None)
        return BedrockEmbeddingProvider(model_id=model)

    # Default: local sentence-transformers
    model = getattr(settings, "embedding_model", DEFAULT_LOCAL_MODEL) or DEFAULT_LOCAL_MODEL
    return SentenceTransformerProvider(model_name=model)
