# Architecture

## System overview

```
User
 │
 ▼
FastAPI
 │
 ▼
Authentication / Authorization
 │
 ▼
Rate Limiting
 │
 ▼
Agent Runtime
 │
 ├──────────────────────────────────────┐
 ▼                                      ▼
LLM Provider (Bedrock)                Tools
 │                                      ├── Tax Calculation Engine
 │                                      ├── Capital Gains Calculator
 │                                      ├── User Financial Data
 │                                      ├── RAG Retrieval
 │                                      └── Document Processing
 ▼
Structured Agent Decision
 │
 ▼
Tool Validation
 │
 ▼
Tool Execution
 │
 ▼
Observation
 │
 ▼
Agent Iteration
 │
 ▼
Final Response + Citations
```

## Layer separation

| Layer | Responsibility |
|-------|----------------|
| LLM | Reasoning, intent extraction, tool selection, explanation |
| RAG | Knowledge retrieval, tax rule lookup |
| Deterministic Engine | Tax arithmetic — no LLM involvement |
| User Data | Financial profile, income, transactions |
| Document Processing | S3 → extraction → chunking → embedding |
| Evaluation | Correctness, faithfulness, retrieval quality |
| Infrastructure | AWS via Terraform |
| Security | Auth, authorization, guardrails |

## Design principles

- **LLM is not the source of truth for calculations.** All tax arithmetic is deterministic Python.
- **Modular monolith.** No unnecessary microservices, Kafka, or service mesh.
- **Cloud-first configuration.** No hardcoded URLs, credentials, or IDs.
- **Progressive complexity.** Raw agent loop first, then LangChain, then LangGraph.
