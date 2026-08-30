"""
Retrieval evaluation metrics — Milestone 19.

Implements:
    Recall@K       — fraction of relevant chunks in top-K
    Precision@K    — fraction of top-K that are relevant
    MRR            — Mean Reciprocal Rank
    NDCG@K         — Normalized Discounted Cumulative Gain

All functions operate on ranked lists of chunk IDs and a set of
relevant chunk IDs — no live services required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalMetrics:
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    k: int
    num_relevant: int
    num_retrieved: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "recall_at_k": round(self.recall_at_k, 4),
            "precision_at_k": round(self.precision_at_k, 4),
            "mrr": round(self.mrr, 4),
            "ndcg_at_k": round(self.ndcg_at_k, 4),
            "k": self.k,
            "num_relevant": self.num_relevant,
            "num_retrieved": self.num_retrieved,
        }


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Recall@K = |Relevant ∩ Retrieved[:K]| / |Relevant|

    Fraction of relevant documents found in the top-K results.
    Returns 0.0 if relevant is empty.
    """
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    return len(top_k & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Precision@K = |Relevant ∩ Retrieved[:K]| / K

    Fraction of the top-K results that are relevant.
    Returns 0.0 if k == 0.
    """
    if k == 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant)
    return hits / k


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """
    Reciprocal Rank = 1 / rank_of_first_relevant_document

    Returns 0.0 if no relevant document appears in the retrieved list.
    Used per-query; MRR averages this over all queries.
    """
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def dcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Discounted Cumulative Gain@K.

    Uses binary relevance (rel=1 if in relevant set, 0 otherwise).
    DCG@K = Σ (2^rel_i - 1) / log2(i + 1)  for i in 1..K
    """
    dcg = 0.0
    for i, doc_id in enumerate(retrieved[:k], start=1):
        rel = 1.0 if doc_id in relevant else 0.0
        dcg += (2 ** rel - 1) / math.log2(i + 1)
    return dcg


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Normalized Discounted Cumulative Gain@K = DCG@K / IDCG@K

    IDCG is the DCG of the ideal (perfect) ranking — all relevant docs first.
    Returns 0.0 if there are no relevant documents.
    """
    if not relevant:
        return 0.0
    actual_dcg = dcg_at_k(retrieved, relevant, k)
    # Ideal: all relevant docs ranked first
    ideal_retrieved = list(relevant)[:k]
    ideal_dcg = dcg_at_k(ideal_retrieved, relevant, k)
    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


def mean_reciprocal_rank(queries: list[tuple[list[str], set[str]]]) -> float:
    """
    Mean Reciprocal Rank over multiple queries.

    Args:
        queries: List of (retrieved_list, relevant_set) tuples.

    Returns:
        MRR averaged over all queries.
    """
    if not queries:
        return 0.0
    rr_sum = sum(reciprocal_rank(retrieved, relevant) for retrieved, relevant in queries)
    return rr_sum / len(queries)


def evaluate_retrieval(
    retrieved: list[str],
    relevant: set[str],
    k: int = 5,
) -> RetrievalMetrics:
    """
    Compute all retrieval metrics for a single query.

    Args:
        retrieved: Ordered list of retrieved chunk IDs (best first).
        relevant:  Set of ground-truth relevant chunk IDs.
        k:         Cut-off for @K metrics.

    Returns:
        RetrievalMetrics dataclass.
    """
    return RetrievalMetrics(
        recall_at_k=recall_at_k(retrieved, relevant, k),
        precision_at_k=precision_at_k(retrieved, relevant, k),
        mrr=reciprocal_rank(retrieved, relevant),
        ndcg_at_k=ndcg_at_k(retrieved, relevant, k),
        k=k,
        num_relevant=len(relevant),
        num_retrieved=len(retrieved),
    )
