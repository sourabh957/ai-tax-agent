"""
Tests for evaluation metrics — Milestone 19.
"""

from __future__ import annotations

import pytest

from app.evaluation.metrics.retrieval import (
    evaluate_retrieval,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.metrics.generation import (
    evaluate_agent,
    evaluate_citation_correctness,
    evaluate_correctness_contains_all,
    evaluate_correctness_exact,
    evaluate_task_completion,
    evaluate_tool_selection,
    evaluate_unnecessary_tool_calls,
)
from app.evaluation.runner import EvaluationRunner


# ── Recall@K ────────────────────────────────────────────────────────────────

def test_recall_perfect():
    assert recall_at_k(["a", "b", "c"], {"a", "b", "c"}, k=3) == 1.0

def test_recall_partial():
    assert recall_at_k(["a", "b", "c"], {"a", "d"}, k=3) == 0.5

def test_recall_zero():
    assert recall_at_k(["a", "b"], {"c", "d"}, k=2) == 0.0

def test_recall_empty_relevant():
    assert recall_at_k(["a"], set(), k=1) == 0.0

def test_recall_k_smaller_than_retrieved():
    # Only top-2 checked, even though 3 retrieved
    assert recall_at_k(["x", "a", "b"], {"a", "b"}, k=2) == 0.5


# ── Precision@K ─────────────────────────────────────────────────────────────

def test_precision_perfect():
    assert precision_at_k(["a", "b", "c"], {"a", "b", "c"}, k=3) == 1.0

def test_precision_partial():
    assert precision_at_k(["a", "x", "b"], {"a", "b"}, k=3) == pytest.approx(2/3)

def test_precision_zero():
    assert precision_at_k(["x", "y"], {"a", "b"}, k=2) == 0.0

def test_precision_k_zero():
    assert precision_at_k([], set(), k=0) == 0.0


# ── MRR ─────────────────────────────────────────────────────────────────────

def test_rr_first_rank():
    assert reciprocal_rank(["a", "b"], {"a"}) == 1.0

def test_rr_second_rank():
    assert reciprocal_rank(["x", "a", "b"], {"a"}) == pytest.approx(0.5)

def test_rr_not_found():
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0

def test_mrr_multiple_queries():
    queries = [
        (["a", "b"], {"a"}),    # RR = 1.0
        (["x", "a"], {"a"}),    # RR = 0.5
    ]
    assert mean_reciprocal_rank(queries) == pytest.approx(0.75)

def test_mrr_empty():
    assert mean_reciprocal_rank([]) == 0.0


# ── NDCG ────────────────────────────────────────────────────────────────────

def test_ndcg_perfect():
    assert ndcg_at_k(["a", "b"], {"a", "b"}, k=2) == pytest.approx(1.0)

def test_ndcg_wrong_order_less_than_perfect():
    # With 3 docs where only the first 2 are relevant:
    # ideal [a, b, x] vs actual [x, a, b] — x is irrelevant so actual is worse
    assert ndcg_at_k(["x", "a", "b"], {"a", "b"}, k=3) < 1.0

def test_ndcg_all_irrelevant():
    assert ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0

def test_ndcg_empty_relevant():
    assert ndcg_at_k(["a", "b"], set(), k=2) == 0.0


# ── evaluate_retrieval ────────────────────────────────────────────────────

def test_evaluate_retrieval_returns_all_metrics():
    m = evaluate_retrieval(["a", "b", "c"], {"a", "c"}, k=3)
    assert 0.0 <= m.recall_at_k <= 1.0
    assert 0.0 <= m.precision_at_k <= 1.0
    assert 0.0 <= m.mrr <= 1.0
    assert 0.0 <= m.ndcg_at_k <= 1.0
    assert m.k == 3


# ── Generation metrics ────────────────────────────────────────────────────

def test_correctness_exact_match():
    assert evaluate_correctness_exact("Your tax is ₹44,200 total.", "₹44,200") == 1.0

def test_correctness_exact_miss():
    assert evaluate_correctness_exact("Your tax is ₹44,200 total.", "₹50,000") == 0.0

def test_correctness_contains_all_partial():
    score = evaluate_correctness_contains_all(
        "New regime saves ₹5,000 and is better.",
        ["new regime", "₹5,000", "old regime"],
    )
    assert score == pytest.approx(2/3)

def test_correctness_contains_all_empty_expected():
    assert evaluate_correctness_contains_all("anything", []) == 1.0

def test_citation_correctness_valid():
    score = evaluate_citation_correctness(
        ["IT Act S.80C FY 2024-25"],
        ["IT Act S.80C", "CBDT Circular"],
    )
    assert score == 1.0

def test_citation_correctness_invalid():
    score = evaluate_citation_correctness(
        ["Made up source 2099"],
        ["IT Act S.80C"],
    )
    assert score == 0.0

def test_citation_correctness_no_citations():
    assert evaluate_citation_correctness([], ["IT Act"]) == 1.0


# ── Agent metrics ─────────────────────────────────────────────────────────

def test_task_completion_true():
    assert evaluate_task_completion("completed", "Your tax is ₹44,200.") is True

def test_task_completion_false_no_answer():
    assert evaluate_task_completion("completed", None) is False

def test_task_completion_false_failed_status():
    assert evaluate_task_completion("failed", "Some answer") is False

def test_tool_selection_perfect():
    assert evaluate_tool_selection(["calculate_tax", "retrieve_tax_rules"],
                                   ["calculate_tax", "retrieve_tax_rules"]) == 1.0

def test_tool_selection_partial():
    assert evaluate_tool_selection(["calculate_tax"], ["calculate_tax", "retrieve_tax_rules"]) == 0.5

def test_tool_selection_empty_expected():
    assert evaluate_tool_selection(["anything"], []) == 1.0

def test_unnecessary_tool_calls():
    count = evaluate_unnecessary_tool_calls(
        ["calculate_tax", "retrieve_tax_rules", "unknown_tool"],
        ["calculate_tax", "retrieve_tax_rules"],
    )
    assert count == 1


# ── Agent state eval (using real AgentState) ──────────────────────────────

def test_evaluate_agent_with_state():
    from app.agents.state import AgentState, ToolCallRecord
    state = AgentState(user_id="u1", user_query="test")
    state.status = "completed"
    state.final_answer = "Your tax is ₹44,200."
    state.iteration_count = 2
    state.tool_call_count = 1
    state.tool_calls = [ToolCallRecord("calculate_tax", {}, {"total_tax": 44200}, True, 50)]

    metrics = evaluate_agent(state, expected_tool_names=["calculate_tax"])
    assert metrics.task_completed is True
    assert metrics.tool_selection_accuracy == 1.0
    assert metrics.tool_argument_accuracy == 1.0
    assert metrics.unnecessary_tool_calls == 0


# ── EvaluationRunner ─────────────────────────────────────────────────────

def test_runner_retrieval_batch():
    runner = EvaluationRunner()
    examples = [
        {"query": "80C limit", "retrieved_ids": ["id1", "id2", "id3"], "relevant_ids": ["id1", "id3"]},
        {"query": "LTCG rate", "retrieved_ids": ["id4", "id5"], "relevant_ids": ["id4"]},
    ]
    report = runner.evaluate_retrieval_batch(examples, k=3)
    assert report.examples_evaluated == 2
    assert 0.0 <= report.mean_recall_at_k <= 1.0
    assert 0.0 <= report.mean_ndcg_at_k <= 1.0


def test_runner_agent_batch():
    from app.agents.state import AgentState, ToolCallRecord
    runner = EvaluationRunner()

    state = AgentState(user_id="u1", user_query="tax query")
    state.status = "completed"
    state.final_answer = "Tax is ₹44,200."
    state.iteration_count = 2
    state.tool_call_count = 1
    state.tool_calls = [ToolCallRecord("calculate_tax", {}, {}, True, 30)]

    report = runner.evaluate_agent_batch(
        [state],
        expected_tool_names_list=[["calculate_tax"]],
        expected_answer_contains_list=[["₹44,200"]],
    )
    assert report.examples_evaluated == 1
    assert report.task_completion_rate == 1.0
    assert report.mean_tool_selection_accuracy == 1.0


def test_runner_empty_batch():
    runner = EvaluationRunner()
    report = runner.evaluate_retrieval_batch([], k=5)
    assert report.examples_evaluated == 0
