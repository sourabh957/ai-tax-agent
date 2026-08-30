"""
Evaluation dataset schemas.

Evaluation requires labelled ground-truth data.
These Pydantic models define the format for eval JSONL files stored at:

    app/evaluation/datasets/retrieval_eval.jsonl
    app/evaluation/datasets/generation_eval.jsonl
    app/evaluation/datasets/agent_eval.jsonl

Each line in a JSONL file is one labelled example.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrievalEvalExample(BaseModel):
    """One labelled retrieval evaluation example."""
    query: str
    relevant_chunk_ids: list[str] = Field(
        description="IDs of chunks that are relevant to this query."
    )
    financial_year: str = "2024-25"
    section: str = ""
    notes: str = ""


class GenerationEvalExample(BaseModel):
    """One labelled generation evaluation example."""
    query: str
    ground_truth_answer: str
    expected_tools: list[str] = Field(
        default_factory=list,
        description="Tool names expected to be called.",
    )
    financial_year: str = "2024-25"
    notes: str = ""


class AgentEvalExample(BaseModel):
    """One labelled agent behaviour evaluation example."""
    query: str
    expected_tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {tool_name, arguments} dicts.",
    )
    expected_final_answer_contains: list[str] = Field(
        default_factory=list,
        description="Strings that must appear in the final answer.",
    )
    max_expected_iterations: int = 5
    notes: str = ""
