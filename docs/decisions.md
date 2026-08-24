# Architectural Decision Records

## ADR-001: Amazon Bedrock as primary LLM provider

**Decision:** Use Amazon Bedrock (not OpenAI) as the default LLM provider.

**Rationale:**
- No long-lived API keys needed in production (IAM role-based access)
- AWS-native integration with ECS/IAM/CloudWatch
- Provider abstraction means OpenAI can be added without changing agent code

---

## ADR-002: Qdrant as vector database

**Decision:** Use Qdrant for initial RAG implementation.

**Rationale:**
- Explicit control over ingestion, chunking, and retrieval
- Self-hostable (Docker for dev, hosted for prod)
- Future migration path: pgvector, OpenSearch, Bedrock Knowledge Bases

---

## ADR-003: PostgreSQL (not SQLite)

**Decision:** PostgreSQL for all relational data.

**Rationale:**
- Production database; SQLite is unsuitable for multi-user concurrent access
- Amazon RDS PostgreSQL is the target production deployment
- Docker Compose provides PostgreSQL locally with zero friction

---

## ADR-004: ECS/Fargate (not Kubernetes/EKS)

**Decision:** ECS Fargate for container orchestration.

**Rationale:**
- Lower operational complexity than EKS for a portfolio/single-team project
- Native AWS integration (IAM, ALB, CloudWatch, ECR)
- Cost scales to zero when no tasks are running

---

## ADR-005: Raw agent loop before LangChain/LangGraph

**Decision:** Implement the agent manually before introducing frameworks.

**Rationale:**
- Forces understanding of the underlying architecture (tool registry, state, loop, termination)
- Makes LangChain abstractions meaningful rather than magical
- Required for FDE/interview explainability

---

## ADR-006: Deterministic tax engine

**Decision:** All tax arithmetic is performed in deterministic Python — the LLM only explains results.

**Rationale:**
- LLMs hallucinate arithmetic
- Tax calculations must be auditable and reproducible
- Tax rules are versioned by financial year

---

## ADR-007: Terraform for infrastructure

**Decision:** All AWS infrastructure is managed via Terraform.

**Rationale:**
- Reproducible environments (dev/prod)
- Version-controlled infrastructure changes
- Enables CI validation (fmt, validate, plan) before apply
