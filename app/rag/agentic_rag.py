"""
Agentic RAG — Milestone 14.

Standard RAG: one retrieval call per request, fixed pipeline.

Agentic RAG: the agent DECIDES when to retrieve, what to retrieve,
and can retrieve multiple times within a single run if the first
retrieval is insufficient.

Architecture:
    Agent iteration
        │
        ▼
    "I need more evidence"
        │
        ▼
    AgenticRAGTool.execute(query, section=...)
        │
        ▼
    hybrid_retrieve() + rerank()
        │
        ▼
    Observation appended to agent state
        │
        ▼
    Agent continues reasoning with new evidence

When to use agentic RAG vs standard RAG:
    Standard:  Simple Q&A, single topic, one retrieval is enough.
    Agentic:   Multi-step tax analysis, regime comparison, multi-section
               queries where the agent discovers it needs additional context
               during reasoning.

This tool is a richer version of RetrieveTaxRulesTool:
    - includes reranking
    - returns citations ready for the final answer
    - tracks how many times retrieval was called (via agent state tool_call_count)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.rag.reranking import CrossEncoderReranker, IdentityReranker, Reranker, extract_citations
from app.rag.retrieval import hybrid_retrieve
from app.tools.base import BaseTool, ToolResult


class AgenticRAGInput(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        description="Specific question or topic to search the tax knowledge base for.",
    )
    financial_year: str = Field(
        default="2024-25",
        description="Financial year to filter by, e.g. '2024-25'.",
    )
    section: str = Field(
        default="",
        description=(
            "IT Act section to narrow the search, e.g. '80C', 'LTCG', '10(38)'. "
            "Leave empty for broad search."
        ),
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of final chunks to return after reranking.",
    )


class AgenticRAGTool(BaseTool):
    """
    Retrieval tool with reranking and citation extraction.

    Used by the agent when it needs high-quality, evidence-backed context.
    The agent can call this multiple times with different queries within
    one run — each call retrieves different evidence.
    """

    def __init__(
        self,
        client,
        collection_name: str,
        embedding_provider,
        reranker: Reranker | None = None,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_provider = embedding_provider
        self._reranker = reranker or IdentityReranker()

    @property
    def name(self) -> str:
        return "retrieve_tax_rules"

    @property
    def description(self) -> str:
        return (
            "Search the Indian tax knowledge base for rules, provisions, sections, "
            "and circulars. Results are reranked for relevance and include citations. "
            "Call this whenever you need to look up specific tax rules, deduction limits, "
            "capital gains provisions, exemptions, or any other tax law detail. "
            "You can call this multiple times with different queries to gather evidence "
            "from different sections."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return AgenticRAGInput

    async def execute(
        self,
        validated_input: AgenticRAGInput,
        *,
        user_id: str,
    ) -> ToolResult:
        try:
            # Step 1: Hybrid retrieval (dense + sparse + RRF)
            result = await hybrid_retrieve(
                validated_input.query,
                client=self._client,
                collection_name=self._collection_name,
                embedding_provider=self._embedding_provider,
                top_k=validated_input.top_k * 2,  # fetch more, reranker trims to top_k
                financial_year=validated_input.financial_year or None,
                section=validated_input.section or None,
                doc_type="tax_rule",
            )

            if not result.chunks:
                return ToolResult.ok({
                    "chunks": [],
                    "total_results": 0,
                    "context_text": "No relevant tax rules found for this query.",
                    "citations": [],
                })

            # Step 2: Rerank
            reranked = await self._reranker.rerank(
                validated_input.query,
                result.chunks,
                top_k=validated_input.top_k,
            )

            # Step 3: Extract citations
            citations = extract_citations(reranked)

            # Step 4: Build output
            output = result.to_dict()
            output["chunks"] = [
                {
                    "id": c.id,
                    "text": c.text,
                    "source": c.source,
                    "score": round(c.score, 4),
                    "rerank_score": c.metadata.get("rerank_score"),
                    "section": c.section,
                    "financial_year": c.financial_year,
                }
                for c in reranked
            ]
            output["total_results"] = len(reranked)
            output["context_text"] = "\n\n---\n\n".join(c.to_context_string() for c in reranked)
            output["citations"] = citations

            return ToolResult.ok(output)

        except Exception as exc:
            return ToolResult.fail(f"Tax rule retrieval failed: {exc}")
