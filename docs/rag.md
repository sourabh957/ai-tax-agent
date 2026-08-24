# RAG Architecture

## Pipeline

```
Upload
  │
  ▼
S3 Storage
  │
  ▼
Extraction (PDF/OCR)
  │
  ▼
Normalization
  │
  ▼
Chunking
  │
  ▼
Metadata tagging
  │
  ▼
Embedding
  │
  ▼
Qdrant
```

## Retrieval stages

| Stage | Description |
|-------|-------------|
| 1 | Basic dense retrieval |
| 2 | Metadata filtering |
| 3 | Hybrid retrieval (dense + sparse) |
| 4 | Reciprocal Rank Fusion (RRF) |
| 5 | Reranking |
| 6 | Citations |
| 7 | Evaluation |

## Agentic RAG

The agent may call `retrieve_tax_rules()` dynamically when it needs additional evidence to answer a query.

## Evaluation metrics

**Retrieval:** Recall@K, Precision@K, MRR, NDCG

**Generation:** faithfulness, answer relevance, correctness, citation correctness
