"""
Document ingestion pipeline — text chunk → embedding → Qdrant.

Pipeline:
    text chunk
        │
        ▼
    EmbeddingProvider.embed()
        │
        ▼
    Qdrant upsert (vector + payload metadata)

This module handles individual chunks. Chunking itself lives in chunking.py.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """
    A single chunk ready for embedding and storage.

    Produced by the chunking pipeline and consumed by ingest_chunk().
    """
    text: str
    source: str                         # e.g. "Income Tax Act 1961 S.80C"
    doc_type: str                       # "tax_rule" | "user_document" | "circular"
    financial_year: str = "2024-25"
    section: str = ""                   # e.g. "80C", "LTCG"
    chunk_index: int = 0
    user_id: str | None = None          # set for user-uploaded documents
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


async def ingest_chunk(
    chunk: DocumentChunk,
    *,
    client,
    collection_name: str,
    embedding_provider,
) -> str:
    """
    Embed a single chunk and upsert it into Qdrant.

    Returns:
        The Qdrant point ID (same as chunk.id).
    """
    from qdrant_client.http import models as qm
    from app.rag.collections import (
        FIELD_CHUNK_INDEX,
        FIELD_CHUNK_TEXT,
        FIELD_DOC_TYPE,
        FIELD_FINANCIAL_YEAR,
        FIELD_SECTION,
        FIELD_SOURCE,
        FIELD_USER_ID,
    )

    vector = await embedding_provider.embed(chunk.text)

    payload: dict[str, Any] = {
        FIELD_CHUNK_TEXT: chunk.text,
        FIELD_SOURCE: chunk.source,
        FIELD_DOC_TYPE: chunk.doc_type,
        FIELD_FINANCIAL_YEAR: chunk.financial_year,
        FIELD_SECTION: chunk.section,
        FIELD_CHUNK_INDEX: chunk.chunk_index,
        **chunk.metadata,
    }
    if chunk.user_id:
        payload[FIELD_USER_ID] = chunk.user_id

    client.upsert(
        collection_name=collection_name,
        points=[
            qm.PointStruct(
                id=chunk.id,
                vector=vector,
                payload=payload,
            )
        ],
    )

    logger.debug(
        "Ingested chunk [id=%s source=%s doc_type=%s]",
        chunk.id, chunk.source, chunk.doc_type,
    )
    return chunk.id


async def ingest_chunks(
    chunks: list[DocumentChunk],
    *,
    client,
    collection_name: str,
    embedding_provider,
    batch_size: int = 32,
) -> list[str]:
    """
    Batch-embed and upsert multiple chunks.

    Uses embed_batch() for efficiency — one model call per batch
    instead of one per chunk.

    Returns:
        List of Qdrant point IDs.
    """
    from qdrant_client.http import models as qm
    from app.rag.collections import (
        FIELD_CHUNK_INDEX,
        FIELD_CHUNK_TEXT,
        FIELD_DOC_TYPE,
        FIELD_FINANCIAL_YEAR,
        FIELD_SECTION,
        FIELD_SOURCE,
        FIELD_USER_ID,
    )

    ids: list[str] = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        vectors = await embedding_provider.embed_batch(texts)

        points = []
        for chunk, vector in zip(batch, vectors):
            payload: dict[str, Any] = {
                FIELD_CHUNK_TEXT: chunk.text,
                FIELD_SOURCE: chunk.source,
                FIELD_DOC_TYPE: chunk.doc_type,
                FIELD_FINANCIAL_YEAR: chunk.financial_year,
                FIELD_SECTION: chunk.section,
                FIELD_CHUNK_INDEX: chunk.chunk_index,
                **chunk.metadata,
            }
            if chunk.user_id:
                payload[FIELD_USER_ID] = chunk.user_id

            points.append(
                qm.PointStruct(id=chunk.id, vector=vector, payload=payload)
            )

        client.upsert(collection_name=collection_name, points=points)
        ids.extend(c.id for c in batch)
        logger.debug("Ingested batch of %d chunks.", len(batch))

    return ids
