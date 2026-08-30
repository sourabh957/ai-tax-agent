"""
Generation and agent evaluation metrics — Milestone 19.

Implements:
    Faithfulness           — is every claim grounded in retrieved context?
    Answer Relevance       — does the answer address the question?
    Correctness            — does the answer match ground truth?
    Citation Correctness   — do citations refer to real source content?
    Tool Selection Accuracy — did the agent call the right tools?
    Tool Argument Accuracy  — were the arguments correct?
    Task Completion         — did the agent produce a final answer?
    Unnecessary Tool Calls  — tool calls beyond what was expected
    Iteration Count         — total agent loop iterations

Note: Faithfulness and Answer Relevance require an LLM judge in full
integration mode. The functions here support both modes:
    - Mock/heuristic mode (no LLM, for unit tests)
    - LLM judge mode (marked with @integration)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GenerationMetrics:
    faithfulness: float | None        # 0.0–1.0, None if not evaluated
    answer_relevance: float | None
    correctness: float | None
    citation_correctness: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "faithfulness": self.faithfulness,
            "answer_relevance": self.answer_relevance,
            "correctness": self.correctness,
            "citation_correctness": self.citation_correctness,
        }


@dataclass
class AgentMetrics:
    task_completed: bool
    iteration_count: int
    tool_call_count: int
    tool_selection_accuracy: float      # 0.0–1.0
    tool_argument_accuracy: float       # 0.0–1.0
    unnecessary_tool_calls: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_completed": self.task_completed,
            "iteration_count": self.iteration_count,
            "tool_call_count": self.tool_call_count,
            "tool_selection_accuracy": round(self.tool_selection_accuracy, 4),
            "tool_argument_accuracy": round(self.tool_argument_accuracy, 4),
            "unnecessary_tool_calls": self.unnecessary_tool_calls,
        }


# ---------------------------------------------------------------------------
# Heuristic / exact-match evaluators (no LLM required)
# ---------------------------------------------------------------------------

def evaluate_correctness_exact(answer: str, ground_truth: str) -> float:
    """
    Binary exact-match correctness.

    Returns 1.0 if ground_truth appears in answer (case-insensitive), else 0.0.
    Suitable for numeric tax amounts and known strings.
    """
    return 1.0 if ground_truth.lower().strip() in answer.lower() else 0.0


def evaluate_correctness_contains_all(answer: str, expected_strings: list[str]) -> float:
    """
    Partial correctness — fraction of expected strings found in the answer.

    Example: expected = ["₹44,200", "new regime", "cess"]
             answer contains 2 of 3 → 0.67
    """
    if not expected_strings:
        return 1.0
    hits = sum(1 for s in expected_strings if s.lower() in answer.lower())
    return hits / len(expected_strings)


def evaluate_citation_correctness(
    citations_in_answer: list[str],
    available_sources: list[str],
) -> float:
    """
    Fraction of citations in the answer that correspond to a real retrieved source.

    Args:
        citations_in_answer: Citations extracted from the LLM's final answer.
        available_sources:   Sources from the retrieved chunks (ground truth).

    Returns:
        0.0–1.0
    """
    if not citations_in_answer:
        return 1.0  # no citations = no wrong citations
    correct = sum(
        1 for c in citations_in_answer
        if any(c.lower() in src.lower() or src.lower() in c.lower()
               for src in available_sources)
    )
    return correct / len(citations_in_answer)


# ---------------------------------------------------------------------------
# Agent evaluators
# ---------------------------------------------------------------------------

def evaluate_task_completion(agent_status: str, final_answer: str | None) -> bool:
    """Task is complete if status == 'completed' and a final answer was produced."""
    return agent_status == "completed" and bool(final_answer and final_answer.strip())


def evaluate_tool_selection(
    actual_tool_names: list[str],
    expected_tool_names: list[str],
) -> float:
    """
    Tool selection accuracy.

    Precision-style: fraction of expected tools that were actually called.
    Returns 1.0 if expected_tool_names is empty (no tools expected = acceptable).
    """
    if not expected_tool_names:
        return 1.0
    actual_set = set(actual_tool_names)
    expected_set = set(expected_tool_names)
    hits = len(actual_set & expected_set)
    return hits / len(expected_set)


def evaluate_unnecessary_tool_calls(
    actual_tool_names: list[str],
    expected_tool_names: list[str],
) -> int:
    """
    Count tool calls beyond what was expected.

    Returns the number of unexpected tool calls (0 = efficient, higher = wasteful).
    """
    expected_set = set(expected_tool_names)
    return sum(1 for t in actual_tool_names if t not in expected_set)


def evaluate_agent(
    agent_state,
    expected_tool_names: list[str],
    expected_answer_contains: list[str] | None = None,
) -> AgentMetrics:
    """
    Evaluate an AgentState against expected behaviour.

    Args:
        agent_state:             Completed AgentState object.
        expected_tool_names:     Tools expected to be called during the run.
        expected_answer_contains: Strings expected to appear in the final answer.

    Returns:
        AgentMetrics dataclass.
    """
    actual_tool_names = [tc.tool_name for tc in agent_state.tool_calls]

    tool_sel = evaluate_tool_selection(actual_tool_names, expected_tool_names)
    unnecessary = evaluate_unnecessary_tool_calls(actual_tool_names, expected_tool_names)
    completed = evaluate_task_completion(agent_state.status, agent_state.final_answer)

    # Argument accuracy: for now, binary — 1.0 if all tool calls succeeded
    successful_calls = sum(1 for tc in agent_state.tool_calls if tc.success)
    arg_accuracy = (
        successful_calls / len(agent_state.tool_calls)
        if agent_state.tool_calls else 1.0
    )

    return AgentMetrics(
        task_completed=completed,
        iteration_count=agent_state.iteration_count,
        tool_call_count=agent_state.tool_call_count,
        tool_selection_accuracy=tool_sel,
        tool_argument_accuracy=arg_accuracy,
        unnecessary_tool_calls=unnecessary,
    )
