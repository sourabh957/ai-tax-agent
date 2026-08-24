"""
Unit tests for reranking, citations, and agentic RAG — Milestones 13 + 14.

All model and Qdrant calls are mocked — no downloads or live services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.reranking import (
    CrossEncoderReranker,
    IdentityReranker,
    extract_citations,
)
from app.rag.retrieval import RetrievedChunk
from app.rag.agentic_rag import AgenticRAGInput, AgenticRAGTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chunk(
    id: str = "1",
    text: str = "Tax rule text",
    source: str = "IT Act",
    score: float = 0.9,
    section: str = "80C",
    fy: str = "2024-25",
) -> RetrievedChunk:
    return RetrievedChunk(
        id=id,
        text=text,
        source=source,
        score=score,
        section=section,
        financial_year=fy,
    )


def make_embedding_provider():
    p = MagicMock()
    p.embed = AsyncMock(return_value=[0.1] * 384)
    p.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 384 for _ in texts])
    return p


def make_qdrant_hit(id: str, text: str = "tax text"):
    hit = MagicMock()
    hit.id = id
    hit.score = 0.9
    hit.payload = {
        "chunk_text": text,
        "source": "IT Act",
        "doc_type": "tax_rule",
        "financial_year": "2024-25",
        "section": "80C",
    }
    return hit


# ---------------------------------------------------------------------------
# IdentityReranker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_identity_reranker_preserves_order():
    chunks = [make_chunk(str(i), score=float(i)) for i in range(5)]
    reranker = IdentityReranker()
    result = await reranker.rerank("query", chunks)
    assert [c.id for c in result] == [c.id for c in chunks]


@pytest.mark.asyncio
async def test_identity_reranker_top_k():
    chunks = [make_chunk(str(i)) for i in range(10)]
    reranker = IdentityReranker()
    result = await reranker.rerank("query", chunks, top_k=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_identity_reranker_empty():
    reranker = IdentityReranker()
    result = await reranker.rerank("query", [])
    assert result == []


# ---------------------------------------------------------------------------
# CrossEncoderReranker (mocked model)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_encoder_reranker_reorders_by_score():
    """CrossEncoder should reorder chunks by the model's relevance scores."""
    chunks = [
        make_chunk("low", text="unrelated content", score=0.8),
        make_chunk("high", text="Section 80C ELSS deduction", score=0.6),
    ]

    reranker = CrossEncoderReranker()

    import numpy as np
    mock_model = MagicMock()
    # high gets score 0.9, low gets score 0.1
    mock_model.predict = MagicMock(return_value=np.array([0.1, 0.9]))
    reranker._model = mock_model

    result = await reranker.rerank("What is 80C deduction?", chunks)

    assert result[0].id == "high"
    assert result[0].metadata["rerank_score"] == 0.9


@pytest.mark.asyncio
async def test_cross_encoder_stores_rerank_score_in_metadata():
    import numpy as np
    chunks = [make_chunk("1", score=0.5)]
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=np.array([0.75]))
    reranker._model = mock_model

    result = await reranker.rerank("query", chunks)
    assert result[0].metadata["rerank_score"] == 0.75


@pytest.mark.asyncio
async def test_cross_encoder_preserves_rrf_score():
    """Original RRF score must be preserved; only metadata gains rerank_score."""
    import numpy as np
    chunks = [make_chunk("1", score=0.123)]
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=np.array([0.9]))
    reranker._model = mock_model

    result = await reranker.rerank("query", chunks)
    assert result[0].score == 0.123     # RRF score unchanged
    assert result[0].metadata["rerank_score"] == 0.9


@pytest.mark.asyncio
async def test_cross_encoder_top_k():
    import numpy as np
    chunks = [make_chunk(str(i)) for i in range(6)]
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=np.array([0.1, 0.9, 0.5, 0.3, 0.8, 0.2]))
    reranker._model = mock_model

    result = await reranker.rerank("query", chunks, top_k=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------

def test_extract_citations_basic():
    chunks = [
        make_chunk("1", source="IT Act", section="80C", fy="2024-25"),
        make_chunk("2", source="CBDT Circular", section="", fy="2024-25"),
    ]
    citations = extract_citations(chunks)
    assert any("80C" in c for c in citations)
    assert any("CBDT Circular" in c for c in citations)


def test_extract_citations_deduplicates():
    chunks = [
        make_chunk("1", source="IT Act", section="80C", fy="2024-25"),
        make_chunk("2", source="IT Act", section="80C", fy="2024-25"),
    ]
    citations = extract_citations(chunks)
    assert len(citations) == 1


def test_extract_citations_empty():
    assert extract_citations([]) == []


def test_extract_citations_no_section():
    chunks = [make_chunk("1", source="CBDT Notification", section="", fy="")]
    citations = extract_citations(chunks)
    assert citations == ["CBDT Notification"]


# ---------------------------------------------------------------------------
# AgenticRAGTool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agentic_rag_tool_success():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[make_qdrant_hit("id-1")])
    client.scroll = MagicMock(return_value=([], None))
    reranker = IdentityReranker()

    tool = AgenticRAGTool(client, "tax_rules", provider, reranker=reranker)
    inp = AgenticRAGInput(query="What is the 80C deduction limit for FY 2024-25?")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is True
    assert "citations" in result.data
    assert "context_text" in result.data
    assert isinstance(result.data["citations"], list)


@pytest.mark.asyncio
async def test_agentic_rag_tool_empty_results():
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[])
    client.scroll = MagicMock(return_value=([], None))

    tool = AgenticRAGTool(client, "tax_rules", provider)
    inp = AgenticRAGInput(query="very obscure query")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is True
    assert result.data["total_results"] == 0
    assert result.data["citations"] == []


@pytest.mark.asyncio
async def test_agentic_rag_tool_exception_returns_failure():
    provider = make_embedding_provider()
    provider.embed = AsyncMock(side_effect=RuntimeError("model down"))
    client = MagicMock()

    tool = AgenticRAGTool(client, "tax_rules", provider)
    inp = AgenticRAGInput(query="any query")
    result = await tool.execute(inp, user_id="u1")

    assert result.success is False
    assert "failed" in result.error


@pytest.mark.asyncio
async def test_agentic_rag_tool_uses_identity_reranker_by_default():
    """Default reranker is IdentityReranker — no model download needed."""
    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[make_qdrant_hit("id-1")])
    client.scroll = MagicMock(return_value=([], None))

    tool = AgenticRAGTool(client, "tax_rules", provider)  # no reranker arg
    assert isinstance(tool._reranker, IdentityReranker)


@pytest.mark.asyncio
async def test_agentic_rag_tool_with_cross_encoder():
    """Verify AgenticRAGTool works correctly when wired with CrossEncoderReranker."""
    import numpy as np

    provider = make_embedding_provider()
    client = MagicMock()
    client.search = MagicMock(return_value=[
        make_qdrant_hit("id-1", text="Section 80C ELSS deduction"),
        make_qdrant_hit("id-2", text="Capital gains tax LTCG"),
    ])
    client.scroll = MagicMock(return_value=([], None))

    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=np.array([0.9, 0.2]))
    reranker._model = mock_model

    tool = AgenticRAGTool(client, "tax_rules", provider, reranker=reranker)
    inp = AgenticRAGInput(query="80C deduction limit", top_k=2)
    result = await tool.execute(inp, user_id="u1")

    assert result.success is True
    # First chunk should be id-1 (rerank_score 0.9)
    assert result.data["chunks"][0]["id"] == "id-1"
