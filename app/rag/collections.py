"""
Qdrant collection management.

Creates / ensures the tax-rules vector collection exists with the correct
configuration. Called once at startup before any ingestion or retrieval.

Collection schema:
    - vector: dense float, cosine similarity
    - payload: chunk_text, source, financial_year, section, doc_type, chunk_index
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Payload field names — centralised so retrieval and ingestion stay in sync
FIELD_CHUNK_TEXT = "chunk_text"
FIELD_SOURCE = "source"
FIELD_FINANCIAL_YEAR = "financial_year"
FIELD_SECTION = "section"
FIELD_DOC_TYPE = "doc_type"
FIELD_CHUNK_INDEX = "chunk_index"
FIELD_USER_ID = "user_id"          # for user-document filtering


def ensure_collection(
    client,
    collection_name: str,
    vector_dimension: int,
) -> None:
    """
    Ensure the Qdrant collection exists with the correct vector config.

    Idempotent — safe to call at every startup.

    Args:
        client:           QdrantClient instance.
        collection_name:  Collection name from QDRANT_COLLECTION env var.
        vector_dimension: Must match the embedding provider's dimension.
    """
    from qdrant_client.http import models as qm

    existing = {c.name for c in client.get_collections().collections}

    if collection_name in existing:
        logger.info("Qdrant collection '%s' already exists.", collection_name)
        return

    logger.info(
        "Creating Qdrant collection '%s' (dim=%d, metric=cosine)",
        collection_name,
        vector_dimension,
    )
    client.create_collection(
        collection_name=collection_name,
        vectors_config=qm.VectorParams(
            size=vector_dimension,
            distance=qm.Distance.COSINE,
        ),
    )

    # Create payload indexes for efficient metadata filtering
    for field in [FIELD_FINANCIAL_YEAR, FIELD_DOC_TYPE, FIELD_USER_ID, FIELD_SECTION]:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )

    logger.info("Collection '%s' created with payload indexes.", collection_name)
