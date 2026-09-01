# Architecture

## Table of contents
- [System overview](#system-overview)
- [Layer separation](#layer-separation)
- [Request lifecycle](#request-lifecycle)
- [Design principles](#design-principles)
- [Technology decisions](#technology-decisions)

---

## System overview

```
User HTTP Request
        │
        ▼
   FastAPI (app/main.py)
        │
        ├── RequestIDMiddleware  →  X-Request-ID header
        ├── CORS Middleware
        │
        ▼
   API Routes (/api/v1/)
        │
        ├── /health, /ready      →  Health probes (ECS / ALB)
        ├── /usage               →  Daily rate limit status
        ├── /documents/upload    →  S3 document upload + extraction
        └── /agent/query         →  Primary agent endpoint
                │
                ▼
        GuardrailPipeline
                │
                ├── Rate limit (per-user daily count)
                ├── Prompt injection detection
                └── Jurisdiction check
                │
                ▼
        AgentLoop (app/agents/loop.py)
                │
                ├──► LLMClient (app/llm/client.py)
                │         └── BedrockProvider / LangChainBedrockProvider
                │
                ├──► ToolRegistry (app/tools/registry.py)
                │         ├── CalculateTaxTool        → TaxEngine (deterministic)
                │         ├── CalculateCapitalGainsTool → CG Engine (deterministic)
                │         └── AgenticRAGTool           → Qdrant hybrid retrieval
                │
                └──► AgentTrace (app/core/observability.py)
                          └── CloudWatch structured logs
```

**AWS infrastructure:**
```
ECR → ECS/Fargate → FastAPI container
                        ├── Amazon Bedrock (LLM)
                        ├── RDS PostgreSQL (user data, agent runs)
                        ├── S3 (uploaded tax documents)
                        ├── Qdrant (vector database, tax rule embeddings)
                        └── Secrets Manager (credentials)
```

---

## Layer separation

| Layer | Responsibility | Files |
|-------|---------------|-------|
| **API** | HTTP routing, request/response schemas, middleware | `app/api/` |
| **Guardrails** | Rate limiting, injection detection, authorization | `app/core/guardrails.py` |
| **Agent** | Reasoning loop, state, decision parsing | `app/agents/` |
| **LLM** | Provider abstraction, Bedrock/LangChain integration | `app/llm/` |
| **Tools** | Agent-callable tools (validated, authorized) | `app/tools/` |
| **RAG** | Chunking, embeddings, Qdrant, hybrid retrieval, reranking | `app/rag/` |
| **Tax Engine** | Deterministic income tax calculations (NO LLM) | `app/services/tax_engine.py` |
| **Capital Gains** | Deterministic capital gains calculations (NO LLM) | `app/services/capital_gains.py` |
| **Documents** | S3 upload, PDF/OCR extraction | `app/documents/` |
| **Database** | SQLAlchemy models, repositories, Alembic migrations | `app/db/` |
| **Evaluation** | Retrieval + generation + agent metrics | `app/evaluation/` |
| **Observability** | Structured tracing, CloudWatch logs, cost tracking | `app/core/observability.py` |
| **Infrastructure** | Terraform modules (VPC, S3, IAM, ECR, ECS, RDS, CloudWatch) | `infra/terraform/` |

---

## Request lifecycle

A complete request through `POST /api/v1/agent/query`:

```
1. Middleware
   RequestIDMiddleware injects X-Request-ID
   CORS headers applied

2. Guardrails (app/core/guardrails.py)
   a. Rate limit check → 429 if exceeded
   b. Prompt injection scan → 400 if detected
   c. Jurisdiction check → warning if non-Indian tax query

3. LLM client resolved
   get_llm_client() → BedrockProvider (or LangChainBedrockProvider)

4. Tool registry built
   CalculateTaxTool, CalculateCapitalGainsTool, AgenticRAGTool (if Qdrant configured)

5. Agent loop (app/agents/loop.py)
   Iteration 1:
     Build messages (system prompt + user query)
     → LLM call (Bedrock) → LLMResponse
     → Parse AgentDecision (FinalAnswer | ToolCall)
     → If ToolCall: validate → execute → observe → continue

   Iteration N:
     ...tool calls with real deterministic engines...
     → LLM produces FinalAnswer with citations

6. Output guardrail
   PII scan on final answer

7. Observability
   AgentTrace.emit() → CloudWatch structured JSON

8. Response
   AgentQueryResponse: request_id, status, final_answer, citations, usage
```

---

## Design principles

### 1. LLM is not the source of truth for calculations
All tax arithmetic and capital gains calculations are deterministic Python.
The LLM only decides *when* to call the tool and *explains* the result.
See [decisions.md](decisions.md#adr-006-deterministic-tax-engine).

### 2. Modular monolith
No unnecessary microservices, Kafka, or service mesh.
The entire system is one deployable unit (ECS Fargate task).

### 3. Cloud-first configuration
No hardcoded URLs, credentials, or IDs anywhere.
Everything is configurable via environment variables.
See [.env.example](../.env.example).

### 4. Progressive complexity
Raw agent loop → LangChain → LangGraph.
Each layer is understood before the next is introduced.
See [langchain_comparison.md](langchain_comparison.md) and [langgraph_comparison.md](langgraph_comparison.md).

### 5. Security at every layer
- Guardrails block injection before the LLM sees the input
- Tools validate all arguments (Pydantic) before execution
- IAM least-privilege (no AdministratorAccess anywhere)
- Secrets in Secrets Manager, never in code or tfstate

---

## Technology decisions

See [decisions.md](decisions.md) for the full ADR (Architectural Decision Record) list.

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| LLM provider | Amazon Bedrock | IAM role auth, no API keys in ECS |
| Vector DB | Qdrant | Self-hostable, explicit RAG control |
| Relational DB | PostgreSQL (RDS) | Production-grade, async SQLAlchemy |
| Container orchestration | ECS/Fargate | Lower ops complexity than EKS |
| IaC | Terraform | Reproducible, version-controlled infrastructure |
| Agent framework | Raw loop first, then LangChain/LangGraph | Interview explainability |
| Embedding model | SentenceTransformers (local) / Bedrock Titan (prod) | Free offline dev, IAM prod |
