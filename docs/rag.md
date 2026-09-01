# RAG Architecture

> See also: [architecture.md](architecture.md) * [evaluation.md](evaluation.md) * [agent.md](agent.md)

## Pipeline overview

```
User document (Form 16, AIS, broker statement)
    |
    v
S3 Storage (app/documents/storage.py)
    |
    v
Extraction (app/documents/extraction.py)
    +-- PDFExtractor   : text from PDF (pypdf)
    +-- ImageExtractor : OCR (pytesseract + Pillow)
    +-- CSVExtractor   : tabular data
    +-- TextExtractor  : plain text
    |
    v
Chunking (app/rag/chunking.py)
    chunk_size=512, overlap=64, min_chunk_size=50
    |
    v
Embedding (app/rag/embeddings.py)
    +-- Dev:  SentenceTransformerProvider (all-MiniLM-L6-v2, 384 dims, free, offline)
    +-- Prod: BedrockEmbeddingProvider (Titan embed-text-v2, 1536 dims, IAM auth)
    |
    v
Qdrant upsert (app/rag/ingestion.py)
    payload: chunk_text, source, financial_year, section, doc_type, user_id
```

---

## Retrieval pipeline (Milestone 11-14)

```
Query
    |
    +-- Dense retrieval    (app/rag/retrieval.py: dense_retrieve())
    |   Qdrant vector similarity search
    |   Metadata filters: financial_year, doc_type, section, user_id
    |
    +-- Sparse retrieval   (app/rag/retrieval.py: sparse_retrieve())
    |   Qdrant full-text scroll (keyword matching)
    |   Falls back gracefully if full-text index not configured
    |
    v
RRF Fusion (app/rag/retrieval.py: _rrf_fuse())
    score(d) = SUM(1 / (60 + rank_i(d)))
    Chunks appearing in both lists get boosted
    |
    v
Reranking (app/rag/reranking.py)
    +-- Dev/test: IdentityReranker (no model, preserves RRF order)
    +-- Prod:     CrossEncoderReranker (ms-marco-MiniLM-L-6-v2)
    |   Cross-encoder jointly scores (query, chunk) pairs
    |   More accurate than bi-encoder similarity alone
    |
    v
Citations (app/rag/reranking.py: extract_citations())
    Format: "Source -- Section (FY)"
    Example: "Income Tax Act 1961 -- Section 80C (FY 2024-25)"
    Deduplicated across all returned chunks
```

---

## Agentic RAG (Milestone 14)

Standard RAG: one fixed retrieval per request.

Agentic RAG: the agent decides WHEN to retrieve, WHAT to retrieve,
and can retrieve multiple times within one run.

```
Agent iteration N:
    "I need the 80C deduction limit"
    -> retrieve_tax_rules(query="80C limit", section="80C")
    -> Observation: chunks with 80C deduction rules

Agent iteration N+1:
    "I also need NPS deduction rules"
    -> retrieve_tax_rules(query="NPS 80CCD deduction", section="80CCD")
    -> Observation: chunks with NPS rules

Agent iteration N+2:
    "Now I have enough to answer"
    -> final_answer(... with citations from both retrievals)
```

File: app/rag/agentic_rag.py (AgenticRAGTool)
The agent can call retrieve_tax_rules multiple times per run.
Each call fetches different evidence.

---

## Two-stage retrieval explanation

Stage 1: RRF (cheap, fast)
- Dense: Qdrant vector search -> top-20 candidates
- Sparse: Qdrant keyword scroll -> top-20 candidates
- RRF fuses both lists: score = 1/(60+rank_dense) + 1/(60+rank_sparse)
- Total cost: 2 Qdrant queries + 1 embedding call

Stage 2: Reranking (expensive, accurate)
- Cross-encoder scores (query, chunk) pairs jointly
- Can capture exact phrase matches, clause references, specific numbers
- Applied only to the top-20 RRF candidates -> returns top-5
- Total cost: 1 model inference call (local)

Why not skip RRF and just rerank everything?
- Reranking 10,000 chunks is too slow (cross-encoder is O(n) per chunk)
- RRF + reranking: fast first pass, accurate second pass

---

## Metadata filtering

Every chunk stored in Qdrant has indexed payload fields:

| Field | Used for |
|-------|---------|
| financial_year | Filter to current FY (e.g. 2024-25) |
| doc_type | Separate tax_rule from user_document |
| section | Narrow search to specific IT Act section |
| user_id | Isolate user-uploaded documents |

Example: retrieve 80C rules for FY 2024-25 only:
    dense_retrieve(query="80C ELSS deduction", financial_year="2024-25", section="80C")

---

## Evaluation metrics

See [evaluation.md](evaluation.md) for full details with formulas and examples.

Quick reference:

| Metric | What it measures |
|--------|-----------------|
| Recall@K | Fraction of relevant chunks in top-K |
| Precision@K | Fraction of top-K that are relevant |
| MRR | Is the most relevant chunk ranked first? |
| NDCG@K | Are more relevant chunks ranked higher? |
| Faithfulness | Is every claim grounded in retrieved context? |
| Citation Correctness | Do citations point to real source content? |

---

## Running the evaluation

```python
from app.evaluation.runner import EvaluationRunner

runner = EvaluationRunner()

# Retrieval evaluation (requires labelled dataset)
examples = [
    {"query": "80C limit", "retrieved_ids": [...], "relevant_ids": ["id1", "id3"]}
]
report = runner.evaluate_retrieval_batch(examples, k=5)
print(report.to_dict())
```