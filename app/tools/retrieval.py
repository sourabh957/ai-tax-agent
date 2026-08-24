"""
RetrieveTaxRulesTool — agent tool that triggers the hybrid RAG pipeline.

The agent calls this when it needs tax rule context to answer a question.
The LLM never directly queries Qdrant — it requests this tool with a query.

Flow:
    Agent decides it needs tax rules
        │
        ▼
    RetrieveTaxRulesTool.execute()
        │
        ▼
    hybrid_retrieve() → dense + sparse + RRF
        │
        ▼
    RetrievalResult → ToolResult with context_text + chunk citations
        │
        ▼
    Agent reads context and forms final answer with citations
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.rag.retrieval import hybrid_retrieve
from app.tools.base import BaseTool, ToolResult


class RetrieveTaxRulesInput(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        description="Natural language search query for tax rules/provisions.",
    )
    financial_year: str = Field(
        default="2024-25",
        description="Financial year to filter results, e.g. '2024-25'.",
    )
    section: str = Field(
        default="",
        description="Specific IT Act section to narrow search, e.g. '80C', 'LTCG'. Leave empty for broad search.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Number of chunks to return (1-15).",
    )


class RetrieveTaxRulesTool(BaseTool):
    def __init__(self, client, collection_name: str, embedding_provider) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_provider = embedding_provider

    @property
    def name(self) -> str:
        return "retrieve_tax_rules"

    @property
    def description(self) -> str:
        return (
            "Search the tax knowledge base for relevant rules, provisions, "
            "sections, and circulars. Use this when you need to look up "
            "specific tax rules, deduction limits, capital gains provisions, "
            "or any other tax law detail. Returns relevant text chunks with sources."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return RetrieveTaxRulesInput

    async def execute(
        self,
        validated_input: RetrieveTaxRulesInput,
        *,
        user_id: str,
    ) -> ToolResult:
        try:
            result = await hybrid_retrieve(
                validated_input.query,
                client=self._client,
                collection_name=self._collection_name,
                embedding_provider=self._embedding_provider,
                top_k=validated_input.top_k,
                financial_year=validated_input.financial_year or None,
                section=validated_input.section or None,
                doc_type="tax_rule",
            )

            if not result.chunks:
                return ToolResult.ok({
                    "chunks": [],
                    "total_results": 0,
                    "context_text": "No relevant tax rules found for this query.",
                    "message": "Knowledge base may not contain rules for this topic yet.",
                })

            return ToolResult.ok(result.to_dict())

        except Exception as exc:
            return ToolResult.fail(f"Tax rule retrieval failed: {exc}")
