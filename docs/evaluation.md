# Evaluation Framework

## Retrieval metrics

| Metric | Description |
|--------|-------------|
| Recall@K | Fraction of relevant documents in top-K |
| Precision@K | Fraction of top-K that are relevant |
| MRR | Mean Reciprocal Rank |
| NDCG | Normalized Discounted Cumulative Gain |

## Generation metrics

| Metric | Description |
|--------|-------------|
| Faithfulness | Answer is grounded in retrieved context |
| Answer relevance | Answer addresses the user's question |
| Correctness | Factual accuracy vs ground truth |
| Citation correctness | Citations point to the actual source |

## Agent metrics

| Metric | Description |
|--------|-------------|
| Tool selection accuracy | Correct tool chosen |
| Tool argument accuracy | Arguments are valid and correct |
| Task completion | Agent successfully answered the question |
| Unnecessary tool calls | Efficiency — fewer is better |
| Iteration count | Efficiency |

## Operational metrics

| Metric | Description |
|--------|-------------|
| Latency | End-to-end request time |
| Token usage | Input + output tokens |
| Estimated cost | Per-request LLM cost |
| Failure rate | Error rate over time |
