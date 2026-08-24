"""
Reranking pipeline — Milestone 13.

After hybrid retrieval + RRF, we have a candidate list ordered by RRF score.
Reranking applies a cross-encoder model that scores (query, chunk) pairs
jointly — more expensive but significantly more accurate than bi-encoder
similarity alone.

Architecture:
    Hybrid retrieve (dense + sparse + RRF)
        │
        ▼
    Reranker (cross-encoder)
        │
        ▼
    Re-ordered chunks with rerank scores
        │
        ▼
    Citation extraction

Providers:
    Local: sentence-transformers cross-encoder (free, offline)
    Production: Can be replaced with Cohere Rerank, BGE reranker, etc.

Why rerank?
    Bi-encoder embeddings compress the full document meaning into a single
    fixed-size vector. A cross-encoder sees query + document together and
    can capture fine-grained relevance signals (e.g. exact section numbers,
    specific clause references) that the bi-encoder misses.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.rag.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker(ABC):
    """Abstract reranker interface."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Rerank chunks by relevance to the query.

        Returns a new list of chunks ordered by rerank score (best first).
        The original RRF scores are preserved in .score; rerank score is in .metadata['rerank_score'].
        """


class CrossEncoderReranker(Reranker):
    """
    Local cross-encoder reranker using sentence-transformers.

    Model: cross-encoder/ms-marco-MiniLM-L-6-v2
        - ~85MB download on first use
        - Strong on passage relevance judgement
        - Free, runs offline
    """

    def __init__(self, model_name: str = DEFAULT_CROSS_ENCODER_MODEL) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                logger.info("Loading CrossEncoder model: %s", self._model_name)
                self._model = CrossEncoder(self._model_name)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        import asyncio

        model = self._load()
        pairs = [(query, chunk.text) for chunk in chunks]

        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None, lambda: model.predict(pairs).tolist()
        )

        reranked = []
        for chunk, score in zip(chunks, scores):
            updated_metadata = {**chunk.metadata, "rerank_score": round(float(score), 4)}
            reranked.append(
                RetrievedChunk(
                    id=chunk.id,
                    text=chunk.text,
                    source=chunk.source,
                    score=chunk.score,       # keep original RRF score
                    doc_type=chunk.doc_type,
                    financial_year=chunk.financial_year,
                    section=chunk.section,
                    metadata=updated_metadata,
                )
            )

        reranked.sort(key=lambda c: c.metadata.get("rerank_score", 0.0), reverse=True)

        if top_k is not None:
            reranked = reranked[:top_k]

        logger.debug(
            "Reranked %d chunks → top %d [model=%s]",
            len(chunks), len(reranked), self._model_name,
        )
        return reranked


class IdentityReranker(Reranker):
    """
    Pass-through reranker — preserves RRF order unchanged.

    Used when:
    - reranking is disabled
    - running unit tests (no model download needed)
    - reranker model is unavailable
    """

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        result = list(chunks)
        if top_k is not None:
            result = result[:top_k]
        return result


def extract_citations(chunks: list[RetrievedChunk]) -> list[str]:
    """
    Extract citation strings from the retrieved chunks.

    A citation identifies the source and section of each chunk used
    to construct the answer. The LLM is given these to include in its response.

    Format: "Source — Section (FY)"

    Example:
        "Income Tax Act 1961 — Section 80C (FY 2024-25)"
    """
    seen: set[str] = set()
    citations: list[str] = []

    for chunk in chunks:
        parts = [chunk.source]
        if chunk.section:
            parts.append(f"Section {chunk.section}")
        if chunk.financial_year:
            parts.append(f"FY {chunk.financial_year}")
        citation = " — ".join(parts)
        if citation not in seen:
            seen.add(citation)
            citations.append(citation)

    return citations
