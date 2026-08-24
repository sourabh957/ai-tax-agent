"""
Unit tests for RAG layer — embeddings, chunking, ingestion.

All external dependencies (Qdrant client, SentenceTransformer) are mocked.
No live services required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.chunking import ChunkConfig, chunk_text
from app.rag.ingestion import DocumentChunk, ingest_chunk, ingest_chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_embedding_provider(dim: int = 384):
    provider = MagicMock()
    provider.dimension = dim
    provider.model_name = "mock-model"
    provider.embed = AsyncMock(return_value=[0.1] * dim)
    provider.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * dim for _ in texts])
    return provider


def make_mock_qdrant_client():
    client = MagicMock()
    client.get_collections.return_value = MagicMock(collections=[])
    client.upsert = MagicMock()
    client.create_collection = MagicMock()
    client.create_payload_index = MagicMock()
    return client


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------

def test_chunk_text_basic():
    text = "A" * 600  # longer than one chunk
    chunks = chunk_text(text, source="test", doc_type="tax_rule")
    assert len(chunks) > 1
    for c in chunks:
        assert "text" in c
        assert "chunk_index" in c
        assert c["source"] == "test"


def test_chunk_text_short_returns_one():
    # text must be >= min_chunk_size (50 chars default)
    text = "This is a short but valid tax rule chunk for testing."
    chunks = chunk_text(text, source="s", doc_type="tax_rule")
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_chunk_text_empty_returns_empty():
    assert chunk_text("", source="s", doc_type="tax_rule") == []


def test_chunk_text_overlap():
    cfg = ChunkConfig(chunk_size=20, chunk_overlap=5, min_chunk_size=5)
    text = "A" * 50
    chunks = chunk_text(text, source="s", doc_type="tax_rule", config=cfg)
    assert len(chunks) > 1


def test_chunk_text_min_size_filter():
    # Very short text should be filtered out if below min_chunk_size
    cfg = ChunkConfig(chunk_size=512, chunk_overlap=64, min_chunk_size=100)
    chunks = chunk_text("tiny", source="s", doc_type="tax_rule", config=cfg)
    assert chunks == []


def test_chunk_preserves_metadata():
    chunks = chunk_text(
        "Under Section 80C of the Income Tax Act, you may claim deductions up to ₹1.5L.",
        source="IT Act S.80C",
        doc_type="tax_rule",
        financial_year="2024-25",
        section="80C",
    )
    assert chunks[0]["financial_year"] == "2024-25"
    assert chunks[0]["section"] == "80C"


# ---------------------------------------------------------------------------
# DocumentChunk tests
# ---------------------------------------------------------------------------

def test_document_chunk_auto_id():
    c1 = DocumentChunk(text="hello", source="s", doc_type="tax_rule")
    c2 = DocumentChunk(text="hello", source="s", doc_type="tax_rule")
    assert c1.id != c2.id  # UUIDs are unique


def test_document_chunk_user_id_optional():
    c = DocumentChunk(text="x", source="s", doc_type="user_document", user_id="u1")
    assert c.user_id == "u1"


# ---------------------------------------------------------------------------
# Ingestion tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_chunk_calls_embed_and_upsert():
    provider = make_mock_embedding_provider()
    client = make_mock_qdrant_client()
    chunk = DocumentChunk(text="Tax rule text", source="IT Act", doc_type="tax_rule")

    result_id = await ingest_chunk(
        chunk,
        client=client,
        collection_name="tax_rules",
        embedding_provider=provider,
    )

    assert result_id == chunk.id
    provider.embed.assert_called_once_with("Tax rule text")
    client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_chunks_batch():
    provider = make_mock_embedding_provider()
    client = make_mock_qdrant_client()
    chunks = [
        DocumentChunk(text=f"Chunk {i}", source="s", doc_type="tax_rule")
        for i in range(5)
    ]

    ids = await ingest_chunks(
        chunks,
        client=client,
        collection_name="tax_rules",
        embedding_provider=provider,
        batch_size=3,
    )

    assert len(ids) == 5
    # 2 batches: 3 + 2
    assert provider.embed_batch.call_count == 2
    assert client.upsert.call_count == 2


@pytest.mark.asyncio
async def test_ingest_chunk_includes_user_id_in_payload():
    provider = make_mock_embedding_provider()
    client = make_mock_qdrant_client()
    chunk = DocumentChunk(
        text="My Form 16 data",
        source="form16.pdf",
        doc_type="user_document",
        user_id="user-abc",
    )

    await ingest_chunk(chunk, client=client, collection_name="col", embedding_provider=provider)

    call_kwargs = client.upsert.call_args.kwargs
    point = call_kwargs["points"][0]
    assert point.payload["user_id"] == "user-abc"


# ---------------------------------------------------------------------------
# Collection management tests
# ---------------------------------------------------------------------------

def test_ensure_collection_creates_when_missing():
    from app.rag.collections import ensure_collection
    client = make_mock_qdrant_client()
    ensure_collection(client, "tax_rules", 384)
    client.create_collection.assert_called_once()


def test_ensure_collection_skips_if_exists():
    from app.rag.collections import ensure_collection
    client = make_mock_qdrant_client()
    # Simulate existing collection
    existing_col = MagicMock()
    existing_col.name = "tax_rules"
    client.get_collections.return_value = MagicMock(collections=[existing_col])

    ensure_collection(client, "tax_rules", 384)
    client.create_collection.assert_not_called()


# ---------------------------------------------------------------------------
# EmbeddingProvider factory test
# ---------------------------------------------------------------------------

def test_get_embedding_provider_returns_local_by_default():
    from app.rag.embeddings import get_embedding_provider, SentenceTransformerProvider
    get_embedding_provider.cache_clear()
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            embedding_provider="local",
            embedding_model=None,
            aws_region="ap-south-1",
        )
        provider = get_embedding_provider()
        assert isinstance(provider, SentenceTransformerProvider)
    get_embedding_provider.cache_clear()


def test_get_qdrant_client_raises_without_url():
    from app.rag.qdrant_store import get_qdrant_client
    get_qdrant_client.cache_clear()
    with patch("app.rag.qdrant_store.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(qdrant_url="", qdrant_api_key="")
        with pytest.raises(RuntimeError, match="QDRANT_URL"):
            get_qdrant_client()
    get_qdrant_client.cache_clear()
