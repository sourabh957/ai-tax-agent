"""
Unit tests for RAG retrieval pipeline — Milestones 11 + 12.

All Qdrant and embedding calls are mocked — no live services required.
Tests cover: dense retrieval, sparse retrieval, RRF fusion, hybrid retrieval,
metadata filtering, RetrieveTaxRulesTool, edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.retrieval import (
    RetrievalResult,
    RetrievedChunk,
    _rrf_fuse,
    dense_retrieve,
    hybrid_retrieve,
    sparse_retrieve,
)
from app.tools.retrieval import RetrieveTaxRulesInput, RetrieveTaxRulesTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_embedding_provider(dim: int = 384):
    p = MagicMock()
    p.embed = AsyncMock(return_value=[0.1] * dim)
    p.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * dim for _ in texts])
    return p


def make_qdrant_hit(id: str, score: float = 0.9, text: str = "tax text", source: str = "IT Act"):
    hit = MagicMock()
    hit.id = id
    hit.score = score
    hit.payload = {
        "chunk_text": text,
        "source": source,
        "doc_type": "tax_rule",
        "financial_year": "2024-25",
        "section": "80C",
    }
    return hit


def make_qdrant_scroll_hit(id: str, text: str = "tax text"):
    r = MagicMock()
    r.id = id
    r.payload = {
        "chunk_text": text,
        "source": "IT Act",
        "doc_type": "tax_rule",
        "financial_year": "2024-25",
        "section": "",
    }
    return r


# ---------------------------------------------------------------------------
# RRF unit tests
# ---------------------------------------------------------------------------

def test_rrf_single_list():
    fused = _rrf_fuse(["a", "b", "c"], [])
    ids = [x[0] for x in fused]
    assert ids == ["a", "b", "c"]


def test_rrf_both_lists_boost_common():
    # "a" appears in both lists → higher combined score
    fused = _rrf_fuse(["a", "b"], ["a", "c"])
    scores = {x[0]: x[1] for x in fused}
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]


def test_rrf_empty_both():
    assert _rrf_fuse([], []) == []


def test_rrf_scores_descending():
    fused = _rrf_fuse(["a", "b", "c"], ["b", "a", "d"])
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_unique_ids_only():
    fused = _rrf_fuse(["a", "b"], ["a", "b"])
    ids = [x[0] for x in fused]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Dense retrieval tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dense_retrieve_calls_qdrant_search():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[
        make_qdrant_hit("id-1", 0.95),
        make_qdrant_hit("id-2", 0.80),
    ])

    results = await dense_retrieve(
        "What is 80C deduction?",
        client=client,
        collection_name="tax_rules",
        embedding_provider=provider,
        top_k=5,
    )

    provider.embed.assert_called_once()
    client.search.assert_called_once()
    assert len(results) == 2
    assert results[0]["id"] == "id-1"


@pytest.mark.asyncio
async def test_dense_retrieve_with_filter():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[])

    await dense_retrieve(
        "query",
        client=client,
        collection_name="col",
        embedding_provider=provider,
        financial_year="2024-25",
        doc_type="tax_rule",
    )

    call_kwargs = client.search.call_args.kwargs
    assert call_kwargs["query_filter"] is not None


# ---------------------------------------------------------------------------
# Sparse retrieval tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sparse_retrieve_returns_results():
    client = MagicMock()
    client.scroll = MagicMock(return_value=(
        [make_qdrant_scroll_hit("id-3"), make_qdrant_scroll_hit("id-4")],
        None,
    ))

    results = await sparse_retrieve(
        "Section 80C ELSS",
        client=client,
        collection_name="tax_rules",
        top_k=5,
    )

    assert len(results) == 2
    assert results[0]["id"] == "id-3"


@pytest.mark.asyncio
async def test_sparse_retrieve_falls_back_on_error():
    client = MagicMock()
    client.scroll = MagicMock(side_effect=RuntimeError("index not found"))

    results = await sparse_retrieve("query", client=client, collection_name="col")
    assert results == []  # graceful fallback


# ---------------------------------------------------------------------------
# Hybrid retrieval tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hybrid_retrieve_returns_retrieval_result():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[make_qdrant_hit("id-1")])
    client.scroll = MagicMock(return_value=([make_qdrant_scroll_hit("id-2")], None))

    result = await hybrid_retrieve(
        "Section 80C",
        client=client,
        collection_name="tax_rules",
        embedding_provider=provider,
        top_k=5,
    )

    assert isinstance(result, RetrievalResult)
    assert len(result.chunks) <= 5
    assert result.query == "Section 80C"
    assert result.total_dense >= 0


@pytest.mark.asyncio
async def test_hybrid_retrieve_rrf_boosts_overlap():
    """A chunk appearing in both dense and sparse should rank highest."""
    provider = make_embedding_provider()
    client = MagicMock()
    # "overlap-id" appears in both lists
    client.search = MagicMock(return_value=[
        make_qdrant_hit("overlap-id", 0.8),
        make_qdrant_hit("dense-only", 0.7),
    ])
    client.scroll = MagicMock(return_value=(
        [make_qdrant_scroll_hit("overlap-id"), make_qdrant_scroll_hit("sparse-only")],
        None,
    ))

    result = await hybrid_retrieve(
        "query",
        client=client,
        collection_name="col",
        embedding_provider=provider,
        top_k=5,
    )

    ids = [c.id for c in result.chunks]
    assert ids[0] == "overlap-id"


@pytest.mark.asyncio
async def test_hybrid_retrieve_empty_results():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[])
    client.scroll = MagicMock(return_value=([], None))

    result = await hybrid_retrieve(
        "query", client=client, collection_name="col", embedding_provider=provider
    )
    assert result.chunks == []


# ---------------------------------------------------------------------------
# RetrievedChunk tests
# ---------------------------------------------------------------------------

def test_retrieved_chunk_context_string():
    c = RetrievedChunk(
        id="1", text="ELSS deduction limit is ₹1.5L.",
        source="IT Act S.80C", score=0.9,
        section="80C", financial_year="2024-25",
    )
    ctx = c.to_context_string()
    assert "IT Act S.80C" in ctx
    assert "80C" in ctx
    assert "ELSS" in ctx


def test_retrieval_result_to_dict():
    r = RetrievalResult(
        chunks=[
            RetrievedChunk(id="1", text="text", source="src", score=0.9)
        ],
        query="q",
        total_dense=3,
        total_sparse=2,
    )
    d = r.to_dict()
    assert d["total_results"] == 1
    assert "context_text" in d
    assert d["chunks"][0]["id"] == "1"


# ---------------------------------------------------------------------------
# RetrieveTaxRulesTool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_tool_success():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[make_qdrant_hit("id-1")])
    client.scroll = MagicMock(return_value=([], None))

    tool = RetrieveTaxRulesTool(client, "tax_rules", provider)
    inp = RetrieveTaxRulesInput(query="What is 80C deduction limit?")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is True
    assert "chunks" in result.data


@pytest.mark.asyncio
async def test_retrieve_tool_empty_returns_ok_with_message():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[])
    client.scroll = MagicMock(return_value=([], None))

    tool = RetrieveTaxRulesTool(client, "tax_rules", provider)
    inp = RetrieveTaxRulesInput(query="obscure query with no results")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is True
    assert result.data["total_results"] == 0


@pytest.mark.asyncio
async def test_retrieve_tool_exception_returns_failure():
    provider = make_embedding_provider()
    provider.embed = AsyncMock(side_effect=RuntimeError("embedding service down"))
    client = MagicMock()

    tool = RetrieveTaxRulesTool(client, "tax_rules", provider)
    inp = RetrieveTaxRulesInput(query="any query")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is False
    assert "failed" in result.error
