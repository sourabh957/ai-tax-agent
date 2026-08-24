# Evaluation Framework

Evaluation is split into four layers: **Retrieval**, **Generation**, **Agent**, and **Operational**.
Each layer tests a different failure mode.

---

## 1. Retrieval Metrics

These measure how well the RAG pipeline finds relevant chunks before the LLM ever sees them.
Poor retrieval = poor answers regardless of LLM quality.

---

### Recall@K

**What it is:** The fraction of all relevant documents that appear in the top-K retrieved results.

**Formula:**
```
Recall@K = |Relevant ∩ Retrieved@K| / |Relevant|
```

**Example:**
- Ground truth: 4 relevant chunks exist for "What is the 80C limit?"
- System retrieves K=5 chunks, 3 of which are relevant
- Recall@5 = 3/4 = 0.75

**What it catches:** Missing relevant context. If Recall@5 is low, the agent will answer
without critical information — even a perfect LLM cannot compensate for missing context.

**How we measure it:** We maintain a labelled eval dataset of (query, relevant_chunk_ids).
We run retrieval and check how many labelled relevant chunks appear in the top-K.

---

### Precision@K

**What it is:** The fraction of the top-K retrieved chunks that are actually relevant.

**Formula:**
```
Precision@K = |Relevant ∩ Retrieved@K| / K
```

**Example:**
- K=5, 2 chunks are relevant → Precision@5 = 2/5 = 0.40

**What it catches:** Noise in the context window. If Precision is low, the LLM is given
irrelevant chunks that can distract it or cause hallucinations.

**Trade-off with Recall:** Retrieving more chunks (larger K) usually improves Recall but
hurts Precision. The reranker's job is to maximise Precision after Recall is satisfied.

---

### MRR — Mean Reciprocal Rank

**What it is:** Measures how high the first relevant document ranks across a set of queries.

**Formula:**
```
MRR = (1/|Q|) × Σ 1/rank_i
```
where `rank_i` is the position of the first relevant document for query i.

**Example:**
- Query 1: first relevant chunk at rank 1 → 1/1 = 1.0
- Query 2: first relevant chunk at rank 3 → 1/3 ≈ 0.33
- MRR = (1.0 + 0.33) / 2 = 0.67

**What it catches:** Whether the most important chunk is near the top.
Particularly important because rerankers and LLMs pay more attention to early context.

---

### NDCG — Normalised Discounted Cumulative Gain

**What it is:** Measures ranking quality when relevance is graded (not just binary).
A chunk at rank 1 is worth more than the same chunk at rank 5.

**Formula:**
```
DCG@K  = Σ (2^rel_i - 1) / log2(i + 1)   for i in 1..K
NDCG@K = DCG@K / IDCG@K
```
where IDCG is the ideal (perfect) ranking's DCG.

**Example with 3 chunks, relevance scores [3, 2, 0]:**
- DCG = (2³-1)/log2(2) + (2²-1)/log2(3) + 0 = 7/1 + 3/1.58 = 8.9
- If ideal order was [3,2,0], IDCG = same → NDCG = 1.0

**What it catches:** Whether the system puts highly-relevant chunks above
mildly-relevant ones. Important for tax where a direct rule citation (highly relevant)
should outrank a tangentially related section.

---

## 2. Generation Metrics

These measure the quality of the LLM's final answer given the retrieved context.

---

### Faithfulness

**What it is:** Whether every claim in the answer is supported by the retrieved context.
An answer is faithful if it contains no information that was not in the retrieved chunks.

**How it is measured:**
1. Extract atomic claims from the answer (e.g. "80C limit is ₹1.5L", "ELSS qualifies").
2. For each claim, verify it can be traced back to a retrieved chunk.
3. Faithfulness = claims_supported / total_claims

**What it catches:** **Hallucination.** The LLM inventing tax rules that are not in the
retrieved context — the most dangerous failure mode for a tax agent.

**Example failure:** Retrieved context says "80C limit is ₹1.5L" but LLM says "₹2L" →
faithfulness = 0 for that claim.

---

### Answer Relevance

**What it is:** Whether the answer actually addresses what the user asked.
A faithful answer can still be irrelevant if it answers a different question.

**How it is measured:**
- Generate N questions from the answer and measure semantic similarity to the original query.
- High similarity → the answer directly addresses the question.

**What it catches:** Answers that are factually correct but miss the point.
E.g. User asks "Should I choose old or new regime?" — agent gives a faithful description
of both regimes but never makes a recommendation or comparison.

---

### Correctness

**What it is:** Whether the answer matches a known ground truth answer.

**How it is measured:**
- Maintain a labelled eval dataset of (query, ground_truth_answer).
- Compare the agent's answer against ground truth using semantic similarity or exact match.
- For numeric claims (tax amounts), use exact comparison.

**What it catches:** Wrong answers. Especially important for tax calculations where
₹44,200 vs ₹44,000 is a meaningful error.

**Note:** For deterministic tax calculations, correctness is measured by comparing
the tax engine output (not LLM output) against known values.

---

### Citation Correctness

**What it is:** Whether the citations in the answer actually refer to a source
that contains the information cited.

**How it is measured:**
- For each citation in the answer (e.g. "IT Act S.80C FY 2024-25"), check that
  the retrieved chunk with that source actually contains the relevant information.

**What it catches:** The LLM inventing or hallucinating citations — citing a section
that doesn't say what the LLM claims it says.

---

## 3. Agent Metrics

These measure the quality of the agent's decision-making — independent of
whether the final answer is correct.

---

### Tool Selection Accuracy

**What it is:** Whether the agent called the right tools for a given query.

**How it is measured:**
- Labelled eval dataset of (query, expected_tools_called).
- Check whether the agent called the expected tools (at any point in the run).
- Example: "Calculate my tax for ₹10L salary" → expected `calculate_tax` to be called.

**What it catches:** Agent calling `retrieve_tax_rules` when it should use
`calculate_tax`, or vice versa. Unnecessary retrievals that bloat latency and cost.

---

### Tool Argument Accuracy

**What it is:** Whether the agent supplied correct arguments to the tools it called.

**How it is measured:**
- For each expected tool call, compare the actual arguments against expected arguments.
- Example: `calculate_tax(gross_income=1000000, regime="new")` — was `regime` correct?

**What it catches:** The agent misinterpreting user input.
E.g. User says "old regime" but agent calls `calculate_tax(regime="new")`.

---

### Task Completion

**What it is:** Binary — did the agent produce a final answer, or did it fail/timeout?

**How it is measured:**
- Check `AgentState.status == "completed"` and `final_answer is not None`.

**What it catches:** Agent getting stuck in loops, timing out, or crashing without
producing any useful output for the user.

---

### Unnecessary Tool Calls

**What it is:** Tool calls made by the agent that were not needed to answer the question.

**How it is measured:**
- `actual_tool_calls - expected_tool_calls`

**What it catches:** Agent over-fetching — calling `retrieve_tax_rules` 5 times
when once was sufficient. Directly impacts latency and token cost.

---

### Iteration Count

**What it is:** Total number of agent loop iterations (LLM calls) per request.

**What it catches:** Efficiency regressions after prompt or tool changes.
An agent that previously answered in 2 iterations now taking 6 is a signal of
degraded decision-making or ambiguous tool descriptions.

---

## 4. Operational Metrics

These measure system health and cost in production.

---

### Latency (P50 / P95 / P99)

**What it is:** End-to-end time from user request to final response, in milliseconds.

**Why percentiles matter:**
- P50 (median) — typical user experience
- P95 — what 1 in 20 users experience
- P99 — tail latency; often caused by slow Qdrant queries or cold model starts

**Components to break down:**
- Embedding latency
- Qdrant retrieval latency
- Reranker latency
- LLM latency (per call + total)
- Tool execution latency

---

### Token Usage

**What it is:** Input tokens + output tokens consumed per request.

**Why it matters:** LLM pricing is per-token. A request with 5 iterations
consumes ~5x the tokens of a 1-iteration request.

**What to track:**
- `total_input_tokens` per request
- `total_output_tokens` per request
- Breakdown by iteration (to identify which step is expensive)

---

### Estimated Cost

**What it is:** Estimated USD cost of a single request based on token usage and
current provider pricing.

**Formula (example for Claude 3.5 Sonnet):**
```
cost = (input_tokens / 1M × $3.00) + (output_tokens / 1M × $15.00)
```

**What to track:**
- Average cost per request
- Cost per session
- Cost trend over time (regressions after prompt changes)

**Why it matters:** A poorly designed prompt that doubles token usage doubles cost.
The `MAX_LLM_CALLS` and `MAX_AGENT_ITERATIONS` limits directly control cost.

---

### Failure Rate

**What it is:** Fraction of requests that end in `status=failed` or `status=timeout`.

**Formula:**
```
failure_rate = failed_requests / total_requests
```

**What it catches:**
- Provider outages (Bedrock timeouts)
- Configuration errors (Qdrant unreachable)
- Agent loop safety limit hits (MAX_ITERATIONS exceeded too frequently)

A rising failure rate after a deployment is the first signal of a regression.

---

## Evaluation dataset

Evaluations require labelled data. We maintain:

```
app/evaluation/datasets/
    retrieval_eval.jsonl     # (query, relevant_chunk_ids, financial_year)
    generation_eval.jsonl    # (query, ground_truth_answer, expected_tools)
    agent_eval.jsonl         # (query, expected_tool_calls, expected_args)
```

Unit tests use mocks. Integration eval tests require:
- A populated Qdrant collection (tax rule chunks ingested)
- A configured LLM provider

Run with:
```bash
pytest -m integration   # integration eval (live services)
pytest -m llm           # LLM eval (paid API)
```
