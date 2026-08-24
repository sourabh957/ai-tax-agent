# AI Tax Agent

A production-oriented AI Tax Agent built as a portfolio project demonstrating:
**LLM integration · RAG · Agent architecture · AWS deployment · Infrastructure as Code**

## Architecture overview

```
User → FastAPI → Auth/Rate limiting → Agent Runtime
                                         ├── Amazon Bedrock (LLM)
                                         ├── Tax Calculation Engine (deterministic)
                                         ├── Capital Gains Calculator (deterministic)
                                         ├── RAG Retrieval (Qdrant)
                                         ├── User Financial Data (PostgreSQL)
                                         └── Document Processing (S3)
```

AWS target: ECS/Fargate · Bedrock · RDS PostgreSQL · S3 · Qdrant · CloudWatch · IAM · ECR

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- AWS CLI configured (`aws configure`)
- Terraform ≥ 1.7

## Quick start (local)

```bash
cp .env.example .env
# Fill in .env values

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Validate configuration
python -m app.core.config_check

# Start local services (PostgreSQL + Qdrant)
docker compose up postgres qdrant -d

# Start API
uvicorn app.main:app --reload
```

## Environment variables

See [`.env.example`](.env.example) for all required/optional variables.

**Never commit `.env` or any file containing real secrets.**

## Docker

```bash
# Full stack (API + PostgreSQL + Qdrant)
docker compose up --build

# API only (requires external DB/Qdrant)
docker compose up api
```

## Configuration check

```bash
python -m app.core.config_check
```

Expected output when fully configured:
```
============================================================
AI Tax Agent — Configuration Check
============================================================
[OK]   Application configuration — env=development, log_level=INFO
[OK]   Database configuration — DATABASE_URL is set
[OK]   Qdrant configuration — QDRANT_URL is set
[OK]   AWS configuration — region=ap-south-1
[OK]   LLM provider — provider=bedrock
[OK]   Bedrock configuration — BEDROCK_MODEL_ID is set
[OK]   Agent limits — iterations=8, tool_calls=10, llm_calls=6
[OK]   Rate limiting — daily_request_limit=5
============================================================
Configuration check passed.
```

## AWS setup

```bash
# Verify AWS identity
aws sts get-caller-identity

# Check configured region
aws configure get region
```

The application uses the **AWS credential chain** — never hardcode credentials.

For production: the ECS task role provides all required AWS permissions.

## Terraform

See [`docs/terraform.md`](docs/terraform.md) for full infrastructure guide.

```bash
cd infra/terraform/environments/dev

terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="dev.tfvars"

# Review plan, then:
terraform apply -var-file="dev.tfvars"
```

> ⚠️ **Never run `terraform apply` without reviewing the plan first.**

## Testing

```bash
# Unit tests (no paid API calls)
pytest tests/unit/

# All tests
pytest

# Integration tests (requires live services)
pytest -m integration

# LLM tests (requires paid API access)
pytest -m llm
```

## Project structure

```
app/
├── api/routes/         FastAPI routers
├── core/               Config, logging, security
├── llm/                LLM abstraction + providers
├── agents/             Agent loop, state, tools
├── tools/              Tax, capital gains, retrieval tools
├── rag/                Ingestion, chunking, retrieval, reranking
├── documents/          S3 upload, extraction
├── db/                 SQLAlchemy models, repositories
├── services/           Business logic services
└── evaluation/         RAG + agent evaluation framework

infra/terraform/
├── modules/            Reusable Terraform modules
└── environments/       dev / prod configurations

docs/                   Architecture + decision records
tests/                  unit / integration / agent / rag
```

## Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Repository + configuration foundation | ✅ |
| 1 | FastAPI + health endpoint | ⬜ |
| 2 | PostgreSQL + SQLAlchemy + Alembic | ⬜ |
| 3 | LLM abstraction | ⬜ |
| 4 | Amazon Bedrock integration | ⬜ |
| 5 | Structured output | ⬜ |
| 6 | Tool registry | ⬜ |
| 7 | Deterministic tax tool | ⬜ |
| 8 | Raw single-agent loop | ⬜ |
| 9 | Agent state | ⬜ |
| 10 | Qdrant + embeddings | ⬜ |
| 11 | Basic RAG | ⬜ |
| 12 | Hybrid retrieval + RRF | ⬜ |
| 13 | Reranking + citations | ⬜ |
| 14 | Agentic RAG | ⬜ |
| 15–41 | See [ai-tax-agent.txt](ai-tax-agent.txt) | ⬜ |

## Security

- Secrets: environment variables only; never in source code
- AWS: IAM roles only; no long-lived access keys in ECS
- LLM output is untrusted; all tool calls are validated server-side
- No arbitrary code execution through tools
