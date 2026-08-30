"""
Evaluation runner — Milestone 19.

Orchestrates evaluation across retrieval, generation, and agent metrics.
Produces a structured report.

Usage:
    runner = EvaluationRunner()
    report = runner.evaluate_retrieval_batch(examples, retrieval_fn)
    report = runner.evaluate_agent_batch(examples, agent_loop)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.evaluation.metrics.retrieval import evaluate_retrieval, RetrievalMetrics
from app.evaluation.metrics.generation import (
    AgentMetrics,
    evaluate_agent,
    evaluate_correctness_contains_all,
    evaluate_citation_correctness,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalEvalReport:
    """Aggregated retrieval evaluation results."""
    examples_evaluated: int
    mean_recall_at_k: float
    mean_precision_at_k: float
    mean_mrr: float
    mean_ndcg_at_k: float
    k: int
    per_example: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "examples_evaluated": self.examples_evaluated,
            "k": self.k,
            "mean_recall_at_k": round(self.mean_recall_at_k, 4),
            "mean_precision_at_k": round(self.mean_precision_at_k, 4),
            "mean_mrr": round(self.mean_mrr, 4),
            "mean_ndcg_at_k": round(self.mean_ndcg_at_k, 4),
        }


@dataclass
class AgentEvalReport:
    """Aggregated agent evaluation results."""
    examples_evaluated: int
    task_completion_rate: float
    mean_tool_selection_accuracy: float
    mean_tool_argument_accuracy: float
    mean_iterations: float
    mean_tool_calls: float
    mean_unnecessary_tool_calls: float
    per_example: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "examples_evaluated": self.examples_evaluated,
            "task_completion_rate": round(self.task_completion_rate, 4),
            "mean_tool_selection_accuracy": round(self.mean_tool_selection_accuracy, 4),
            "mean_tool_argument_accuracy": round(self.mean_tool_argument_accuracy, 4),
            "mean_iterations": round(self.mean_iterations, 2),
            "mean_tool_calls": round(self.mean_tool_calls, 2),
            "mean_unnecessary_tool_calls": round(self.mean_unnecessary_tool_calls, 2),
        }


class EvaluationRunner:
    """
    Orchestrates evaluation runs.

    Methods:
        evaluate_retrieval_batch  — runs Recall/Precision/MRR/NDCG on labelled examples
        evaluate_agent_batch      — runs agent metrics on completed AgentState objects
    """

    def evaluate_retrieval_batch(
        self,
        examples: list[dict[str, Any]],
        k: int = 5,
    ) -> RetrievalEvalReport:
        """
        Evaluate retrieval quality on a batch of labelled examples.

        Args:
            examples: List of dicts with keys:
                        - retrieved_ids: list[str]  (ordered, best first)
                        - relevant_ids:  list[str]  (ground truth)
                        - query:         str
            k: Cut-off for @K metrics.

        Returns:
            RetrievalEvalReport with per-example and aggregate metrics.
        """
        all_metrics: list[RetrievalMetrics] = []
        per_example = []

        for ex in examples:
            retrieved = ex.get("retrieved_ids", [])
            relevant = set(ex.get("relevant_ids", []))
            query = ex.get("query", "")

            m = evaluate_retrieval(retrieved, relevant, k=k)
            all_metrics.append(m)
            per_example.append({"query": query, **m.to_dict()})

        n = len(all_metrics)
        if n == 0:
            return RetrievalEvalReport(0, 0.0, 0.0, 0.0, 0.0, k)

        return RetrievalEvalReport(
            examples_evaluated=n,
            mean_recall_at_k=sum(m.recall_at_k for m in all_metrics) / n,
            mean_precision_at_k=sum(m.precision_at_k for m in all_metrics) / n,
            mean_mrr=sum(m.mrr for m in all_metrics) / n,
            mean_ndcg_at_k=sum(m.ndcg_at_k for m in all_metrics) / n,
            k=k,
            per_example=per_example,
        )

    def evaluate_agent_batch(
        self,
        agent_states: list[Any],
        expected_tool_names_list: list[list[str]],
        expected_answer_contains_list: list[list[str]] | None = None,
    ) -> AgentEvalReport:
        """
        Evaluate a batch of completed AgentState objects.

        Args:
            agent_states:               List of completed AgentState objects.
            expected_tool_names_list:   Expected tool names per example.
            expected_answer_contains_list: Expected answer substrings per example.

        Returns:
            AgentEvalReport with aggregate metrics.
        """
        if expected_answer_contains_list is None:
            expected_answer_contains_list = [[] for _ in agent_states]

        all_metrics: list[AgentMetrics] = []
        per_example = []

        for state, exp_tools, exp_answer in zip(
            agent_states, expected_tool_names_list, expected_answer_contains_list
        ):
            m = evaluate_agent(state, exp_tools)
            all_metrics.append(m)

            # Correctness check on answer
            correctness = evaluate_correctness_contains_all(
                state.final_answer or "", exp_answer
            )
            per_example.append({
                "request_id": state.request_id,
                "answer_correctness": round(correctness, 4),
                **m.to_dict(),
            })

        n = len(all_metrics)
        if n == 0:
            return AgentEvalReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        return AgentEvalReport(
            examples_evaluated=n,
            task_completion_rate=sum(1 for m in all_metrics if m.task_completed) / n,
            mean_tool_selection_accuracy=sum(m.tool_selection_accuracy for m in all_metrics) / n,
            mean_tool_argument_accuracy=sum(m.tool_argument_accuracy for m in all_metrics) / n,
            mean_iterations=sum(m.iteration_count for m in all_metrics) / n,
            mean_tool_calls=sum(m.tool_call_count for m in all_metrics) / n,
            mean_unnecessary_tool_calls=sum(m.unnecessary_tool_calls for m in all_metrics) / n,
            per_example=per_example,
        )
