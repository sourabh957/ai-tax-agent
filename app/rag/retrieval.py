"""
RAG retrieval pipeline — Milestones 11 + 12.

Implements:
    11. Basic dense retrieval with metadata filtering
    12. Hybrid retrieval (dense + sparse) with Reciprocal Rank Fusion (RRF)

Architecture:
    Query
      │
      ├─► Dense retrieval  (semantic similarity via Qdrant)
      │
      └─► Sparse retrieval (BM25-style keyword via Qdrant full-text search)
                │
                ▼
           RRF fusion
                │
                ▼
          Ranked results
                │
                ▼
          RetrievedChunk list  (fed to reranker in Milestone 13)

Why RRF?
    Dense retrieval is strong on semantic similarity but can miss exact keyword
    matches (e.g. "Section 80C", "LTCG", specific form names).
    Sparse retrieval catches exact terms but misses paraphrase.
    RRF combines both ranked lists without needing score normalisation.

    RRF formula: score(d) = Σ 1 / (k + rank_i(d))
    k=60 is the standard default (Cormack et al. 2009).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

RRF_K = 60  # standard RRF constant


@dataclass
class RetrievedChunk:
    """A single chunk returned by the retrieval pipeline."""

    id: str
    text: str
    source: str
    score: float                          # RRF score (higher = more relevant)
    doc_type: str = ""
    financial_year: str = ""
    section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_string(self) -> str:
        """Format for insertion into the LLM context window."""
        parts = [f"[Source: {self.source}]"]
        if self.section:
            parts.append(f"[Section: {self.section}]")
        if self.financial_year:
            parts.append(f"[FY: {self.financial_year}]")
        parts.append(self.text)
        return "\n".join(parts)


@dataclass
class RetrievalResult:
    """Full retrieval result returned to the agent."""

    chunks: list[RetrievedChunk]
    query: str
    total_dense: int = 0
    total_sparse: int = 0

    @property
    def context_text(self) -> str:
        """Concatenate all chunks into a single context block."""
        return "\n\n---\n\n".join(c.to_context_string() for c in self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunks": [
                {
                    "id": c.id,
                    "text": c.text,
                    "source": c.source,
                    "score": round(c.score, 4),
                    "section": c.section,
                    "financial_year": c.financial_year,
                }
                for c in self.chunks
            ],
            "total_results": len(self.chunks),
            "context_text": self.context_text,
        }


def _build_filter(
    financial_year: str | None = None,
    doc_type: str | None = None,
    user_id: str | None = None,
    section: str | None = None,
):
    """Build a Qdrant filter from optional metadata constraints."""
    from qdrant_client.http import models as qm
    from app.rag.collections import (
        FIELD_DOC_TYPE,
        FIELD_FINANCIAL_YEAR,
        FIELD_SECTION,
        FIELD_USER_ID,
    )

    conditions = []
    if financial_year:
        conditions.append(
            qm.FieldCondition(
                key=FIELD_FINANCIAL_YEAR,
                match=qm.MatchValue(value=financial_year),
            )
        )
    if doc_type:
        conditions.append(
            qm.FieldCondition(key=FIELD_DOC_TYPE, match=qm.MatchValue(value=doc_type))
        )
    if user_id:
        conditions.append(
            qm.FieldCondition(key=FIELD_USER_ID, match=qm.MatchValue(value=user_id))
        )
    if section:
        conditions.append(
            qm.FieldCondition(key=FIELD_SECTION, match=qm.MatchValue(value=section))
        )

    if not conditions:
        return None
    return qm.Filter(must=conditions)


def _rrf_fuse(
    dense_ids: list[str],
    sparse_ids: list[str],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion of two ranked lists.

    Args:
        dense_ids:  IDs ordered by dense similarity (best first).
        sparse_ids: IDs ordered by sparse/keyword relevance (best first).
        k:          RRF constant (default 60).

    Returns:
        List of (id, rrf_score) sorted by score descending.
    """
    scores: dict[str, float] = {}

    for rank, doc_id in enumerate(dense_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    for rank, doc_id in enumerate(sparse_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


async def dense_retrieve(
    query: str,
    *,
    client,
    collection_name: str,
    embedding_provider,
    top_k: int = 10,
    financial_year: str | None = None,
    doc_type: str | None = None,
    user_id: str | None = None,
    section: str | None = None,
) -> list[dict[str, Any]]:
    """
    Dense semantic retrieval using Qdrant vector similarity search.

    Returns raw Qdrant hits as dicts (id, score, payload).
    """
    import asyncio

    vector = await embedding_provider.embed(query)
    qdrant_filter = _build_filter(financial_year, doc_type, user_id, section)

    loop = asyncio.get_event_loop()
    hits = await loop.run_in_executor(
        None,
        lambda: client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        ),
    )

    return [
        {"id": str(h.id), "score": h.score, "payload": h.payload}
        for h in hits
    ]


async def sparse_retrieve(
    query: str,
    *,
    client,
    collection_name: str,
    top_k: int = 10,
    financial_year: str | None = None,
    doc_type: str | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Sparse keyword retrieval using Qdrant full-text search.

    Qdrant supports full-text payload search via scroll + text matching.
    This is a BM25-approximate approach using Qdrant's keyword index.

    Note: Requires a full-text index on FIELD_CHUNK_TEXT.
    Falls back to empty list if the index is not configured (non-blocking).
    """
    import asyncio
    from app.rag.collections import FIELD_CHUNK_TEXT

    qdrant_filter = _build_filter(financial_year, doc_type, user_id)

    try:
        from qdrant_client.http import models as qm

        # Build text match condition
        text_condition = qm.FieldCondition(
            key=FIELD_CHUNK_TEXT,
            match=qm.MatchText(text=query),
        )

        if qdrant_filter:
            combined = qm.Filter(must=qdrant_filter.must + [text_condition])
        else:
            combined = qm.Filter(must=[text_condition])

        loop = asyncio.get_event_loop()
        results, _ = await loop.run_in_executor(
            None,
            lambda: client.scroll(
                collection_name=collection_name,
                scroll_filter=combined,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            ),
        )
        return [{"id": str(r.id), "score": 1.0, "payload": r.payload} for r in results]

    except Exception as exc:
        logger.warning(
            "Sparse retrieval failed (full-text index may not be configured): %s", exc
        )
        return []


async def hybrid_retrieve(
    query: str,
    *,
    client,
    collection_name: str,
    embedding_provider,
    top_k: int = 5,
    dense_k: int = 10,
    sparse_k: int = 10,
    financial_year: str | None = None,
    doc_type: str | None = None,
    user_id: str | None = None,
    section: str | None = None,
) -> RetrievalResult:
    """
    Hybrid retrieval: dense + sparse → RRF fusion → top-k results.

    Args:
        top_k:    Final number of chunks to return after RRF.
        dense_k:  How many candidates to fetch from dense retrieval.
        sparse_k: How many candidates to fetch from sparse retrieval.

    Returns:
        RetrievalResult with fused, ranked chunks.
    """
    import asyncio
    from app.rag.collections import FIELD_CHUNK_TEXT, FIELD_SOURCE, FIELD_SECTION, FIELD_FINANCIAL_YEAR, FIELD_DOC_TYPE

    # Run dense and sparse in parallel
    dense_task = dense_retrieve(
        query,
        client=client,
        collection_name=collection_name,
        embedding_provider=embedding_provider,
        top_k=dense_k,
        financial_year=financial_year,
        doc_type=doc_type,
        user_id=user_id,
        section=section,
    )
    sparse_task = sparse_retrieve(
        query,
        client=client,
        collection_name=collection_name,
        top_k=sparse_k,
        financial_year=financial_year,
        doc_type=doc_type,
        user_id=user_id,
    )

    dense_hits, sparse_hits = await asyncio.gather(dense_task, sparse_task)

    # Build lookup maps
    all_hits: dict[str, dict] = {}
    for h in dense_hits + sparse_hits:
        all_hits[h["id"]] = h

    dense_ids = [h["id"] for h in dense_hits]
    sparse_ids = [h["id"] for h in sparse_hits]

    # RRF fusion
    fused = _rrf_fuse(dense_ids, sparse_ids)[:top_k]

    chunks = []
    for doc_id, rrf_score in fused:
        hit = all_hits.get(doc_id, {})
        payload = hit.get("payload") or {}
        chunks.append(
            RetrievedChunk(
                id=doc_id,
                text=payload.get(FIELD_CHUNK_TEXT, ""),
                source=payload.get(FIELD_SOURCE, ""),
                score=rrf_score,
                doc_type=payload.get(FIELD_DOC_TYPE, ""),
                financial_year=payload.get(FIELD_FINANCIAL_YEAR, ""),
                section=payload.get(FIELD_SECTION, ""),
                metadata={k: v for k, v in payload.items()
                          if k not in (FIELD_CHUNK_TEXT, FIELD_SOURCE)},
            )
        )

    logger.debug(
        "Hybrid retrieve [query=%r dense=%d sparse=%d fused=%d]",
        query[:60], len(dense_hits), len(sparse_hits), len(chunks),
    )

    return RetrievalResult(
        chunks=chunks,
        query=query,
        total_dense=len(dense_hits),
        total_sparse=len(sparse_hits),
    )
