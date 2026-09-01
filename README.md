# AI Tax Agent

A **production-oriented AI Tax Agent** demonstrating end-to-end AI engineering:
LLM reasoning · RAG · deterministic tax engines · agent orchestration · AWS infrastructure · IaC

> **Portfolio project** for demonstrating: Production AI Engineering · LLM Integration ·
> Structured Outputs · Tool Calling · Agent Architecture · RAG · Hybrid Retrieval ·
> Reranking · Agentic RAG · Evaluation · Guardrails · Observability · AWS Deployment ·
> Infrastructure as Code · LangChain · LangGraph

---

## Table of Contents

- [What this is](#what-this-is)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Quick start (local)](#quick-start-local)
- [Environment variables](#environment-variables)
- [Running the agent](#running-the-agent)
- [Configuration check](#configuration-check)
- [Docker](#docker)
- [Database setup](#database-setup)
- [Bedrock setup](#bedrock-setup)
- [Qdrant setup](#qdrant-setup)
- [Testing](#testing)
- [Terraform infrastructure](#terraform-infrastructure)
- [AWS deployment](#aws-deployment)
- [Observability](#observability)
- [Evaluation](#evaluation)
- [Security](#security)
- [Cost control](#cost-control)
- [Milestones](#milestones)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)

---

## What this is

The AI Tax Agent accepts natural language tax questions and responds with:
- Accurate tax calculations (deterministic Python — not LLM guesses)
- Regime comparison (new vs old)
- Capital gains analysis (equity, debt MF, foreign stocks, Budget 2024 rates)
- Document-grounded answers with citations (RAG from tax rules knowledge base)

**Example query:**
> "I earn ₹30L salary, have ₹2L equity LTCG, invested ₹1.5L in ELSS and ₹50K in NPS.
> Compare my tax liability under both regimes for FY 2024-25."

**What happens internally:**
```
Intent extraction
    → retrieve_tax_rules("80C deduction", "NPS 80CCD")    [RAG]
    → calculate_tax(30L, old regime, deductions=2L)        [deterministic]
    → calculate_tax(30L, new regime)                       [deterministic]
    → calculate_capital_gains([LTCG 2L equity])            [deterministic]
    → final_answer(comparison + citations)
```

---

## Architecture

```
User → POST /api/v1/agent/query
         │
    GuardrailPipeline (rate limit, injection check, jurisdiction)
         │
    AgentLoop
    ┌────┴─────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
Amazon Bedrock (LLM)                          ToolRegistry
    │                                         ├── calculate_tax        (₹ deterministic)
    ▼                                         ├── calculate_capital_gains (₹ deterministic)
AgentDecision                                 └── retrieve_tax_rules   (Qdrant RAG)
    │
    ├── FinalAnswer → response with citations
    └── ToolCall → execute → observe → iterate
         │
    AgentTrace → CloudWatch structured logs
```

Full architecture diagram: [docs/architecture.md](docs/architecture.md)

**AWS target:**
```
ECR → ECS Fargate → FastAPI
                      ├── Amazon Bedrock    (LLM inference)
                      ├── RDS PostgreSQL    (user data, agent runs)
                      ├── S3               (uploaded tax documents)
                      ├── Qdrant           (tax rule vector store)
                      └── Secrets Manager  (credentials)
```

---

## Project structure

```
app/
├── api/
│   ├── routes/
│   │   ├── agent.py          POST /agent/query — main agent endpoint
│   │   ├── documents.py      POST /documents/upload
│   │   ├── health.py         GET /health, /ready
│   │   └── usage.py          GET /usage
│   └── middleware.py         X-Request-ID injection
│
├── agents/
│   ├── loop.py               Raw agent loop (Milestone 8)
│   ├── state.py              AgentState — per-run context
│   ├── schemas.py            AgentDecision (FinalAnswer | ToolCall)
│   └── langgraph_agent.py    LangGraph implementation (Milestone 26)
│
├── llm/
│   ├── base.py               LLMProvider abstract interface
│   ├── client.py             LLMClient factory
│   ├── schemas.py            Message, LLMResponse, ToolDefinition
│   ├── langchain_tools.py    @tool wrappers for LangChain
│   └── providers/
│       ├── bedrock.py        Amazon Bedrock (boto3 converse API)
│       └── langchain_bedrock.py  LangChain ChatBedrock
│
├── tools/
│   ├── base.py               BaseTool + ToolResult
│   ├── registry.py           ToolRegistry with authorization
│   ├── tax.py                CalculateTaxTool
│   ├── capital_gains.py      CalculateCapitalGainsTool
│   └── retrieval.py          RetrieveTaxRulesTool
│
├── rag/
│   ├── embeddings.py         EmbeddingProvider (local ST / Bedrock Titan)
│   ├── chunking.py           Overlapping text chunker
│   ├── ingestion.py          Chunk → embed → Qdrant upsert
│   ├── collections.py        Qdrant collection management
│   ├── retrieval.py          Dense + sparse + RRF hybrid retrieval
│   ├── reranking.py          CrossEncoder reranker + citations
│   ├── agentic_rag.py        AgenticRAGTool (retrieval + rerank + citations)
│   └── qdrant_store.py       Qdrant client factory
│
├── services/
│   ├── tax_engine.py         Deterministic Indian tax calculator (FY 2024-25)
│   └── capital_gains.py      Deterministic capital gains (Budget 2024 rates)
│
├── documents/
│   ├── storage.py            S3 upload/download, presigned URLs
│   └── extraction.py         PDF / OCR / CSV / text extractors
│
├── db/
│   ├── base.py               SQLAlchemy declarative base
│   ├── session.py            Async engine + session factory
│   ├── models/               User, TaxProfile, AgentRun
│   └── repositories/         UserRepository, BaseRepository
│
├── evaluation/
│   ├── metrics/
│   │   ├── retrieval.py      Recall@K, Precision@K, MRR, NDCG
│   │   └── generation.py     Faithfulness, Correctness, Tool accuracy
│   └── runner.py             EvaluationRunner (batch retrieval + agent eval)
│
└── core/
    ├── config.py             Pydantic Settings (all env vars)
    ├── config_check.py       python -m app.core.config_check
    ├── bedrock_check.py      Bedrock IAM access validation
    ├── guardrails.py         Rate limiting, injection, tool authorization
    ├── observability.py      AgentTrace → CloudWatch structured logs
    ├── cost_tracking.py      Token cost estimates
    ├── hardening.py          Production startup checks
    ├── logging.py            Structured logging setup
    └── secrets.py            Secrets Manager integration

infra/terraform/
├── modules/
│   ├── networking/           VPC, subnets, security groups
│   ├── s3/                   Encrypted S3 bucket
│   ├── iam/                  ECS execution + task roles (least privilege)
│   ├── ecr/                  Container registry + lifecycle policy
│   ├── rds/                  PostgreSQL 16, private subnets, Secrets Manager
│   ├── ecs/                  Fargate cluster + task definition + service
│   └── cloudwatch/           Log groups, metric alarms, Insights queries
└── environments/
    ├── dev/                  Dev environment (all modules wired)
    └── prod/                 Prod environment (separate state)

.github/workflows/
├── ci.yml                    Tests + Terraform validate + Docker build
├── deploy.yml                Build → ECR → ECS (OIDC, no long-lived keys)
└── terraform-plan.yml        PR plan comment (never auto-apply)

scripts/
├── deploy_ecr.sh             Build and push Docker image to ECR
├── deploy_ecs.sh             Full ECS deployment with rollback
├── validate_terraform.sh     fmt + validate + plan (CI-safe)
└── run_tests.sh              Unit → integration → LLM (opt-in)

docs/
├── architecture.md           System design, request lifecycle, layer separation
├── agent.md                  Raw agent loop, state, tool registry
├── rag.md                    RAG pipeline, hybrid retrieval, evaluation
├── langchain_comparison.md   Raw vs LangChain — when/why/trade-offs
├── langgraph_comparison.md   LangGraph — stateful workflows, human-in-loop
├── terraform.md              Infrastructure guide, commands, cost awareness
├── deployment.md             ECR push, ECS deploy, rollback
├── production_config.md      Production checklist, secrets, CORS, migrations
├── evaluation.md             All metrics explained with formulas and examples
└── decisions.md              Architectural Decision Records (ADRs)
```

---

## Quick start (local)

```bash
# 1. Clone and enter the project
git clone https://github.com/sourabh957/ai-tax-agent.git
cd ai-tax-agent

# 2. Copy and configure environment
cp .env.example .env
# Edit .env — minimum for local dev:
#   APP_ENV=development
#   LOG_LEVEL=INFO
#   LLM_PROVIDER=bedrock
#   BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
#   AWS_REGION=ap-south-1

# 3. Create virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Validate configuration
python -m app.core.config_check

# 6. Start local services (PostgreSQL + Qdrant)
docker compose up postgres qdrant -d

# 7. Run database migrations
alembic upgrade head

# 8. Start the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger UI.

---

## Environment variables

Copy `.env.example` to `.env` and fill in values. See inline comments for each variable.

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_ENV` | Yes | `development` / `staging` / `production` |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` (default: INFO) |
| `DATABASE_URL` | For DB ops | `postgresql+asyncpg://user:pass@host/db` |
| `QDRANT_URL` | For RAG | `http://localhost:6333` or Qdrant Cloud URL |
| `QDRANT_API_KEY` | For RAG | Qdrant Cloud API key (empty for local) |
| `QDRANT_COLLECTION` | For RAG | Collection name, e.g. `tax_rules` |
| `AWS_REGION` | For Bedrock/S3 | e.g. `ap-south-1` |
| `S3_BUCKET_NAME` | For uploads | S3 bucket name for tax documents |
| `LLM_PROVIDER` | For agent | `bedrock` or `langchain_bedrock` |
| `BEDROCK_MODEL_ID` | For Bedrock | e.g. `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `MAX_AGENT_ITERATIONS` | No | Hard stop on agent iterations (default: 8) |
| `MAX_TOOL_CALLS` | No | Hard stop on tool calls per request (default: 10) |
| `MAX_LLM_CALLS` | No | Hard stop on LLM API calls (default: 6) |
| `DAILY_REQUEST_LIMIT` | No | Per-user daily request cap (default: 5) |

> **Never commit `.env`.** It is in `.gitignore`. Use `.env.example` as a template.

---

## Running the agent

```bash
# Ask a tax question
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is my income tax for ₹10 lakh salary under new regime FY 2024-25?",
    "financial_year": "2024-25"
  }'

# Response:
{
  "request_id": "...",
  "status": "completed",
  "final_answer": "Your total tax under the new regime is ₹44,200...",
  "citations": ["Indian Income Tax Act — standard deduction FY 2024-25"],
  "usage": {
    "input_tokens": 450, "output_tokens": 120,
    "estimated_cost_usd": 0.00315
  },
  "warnings": []
}
```

---

## Configuration check

```bash
python -m app.core.config_check
```

Expected output (fully configured):
```
============================================================
AI Tax Agent — Configuration Check
============================================================
[OK]   Application configuration — env=development, log_level=INFO
[OK]   Database configuration — DATABASE_URL is set
[OK]   Qdrant configuration — QDRANT_URL is set
[OK]   AWS configuration — region=ap-south-1
[OK]   S3 configuration — S3_BUCKET_NAME is set
[OK]   LLM provider — provider=bedrock
[OK]   Bedrock configuration — BEDROCK_MODEL_ID is set
[OK]   Bedrock: AWS credentials — account=123456789012
[OK]   Bedrock: Bedrock model listed — Model available in ap-south-1
[OK]   Agent limits — iterations=8, tool_calls=10, llm_calls=6
[OK]   Rate limiting — daily_request_limit=5
============================================================
Configuration check passed.
```

---

## Docker

```bash
# Start all services (API + PostgreSQL + Qdrant)
docker compose up --build

# API only (requires external DB + Qdrant)
docker compose up api

# Stop and remove containers
docker compose down

# Production image build (multi-stage, non-root user)
docker build -t ai-tax-agent:latest .
```

The production Dockerfile uses:
- Multi-stage build (builder + production image, no compiler in prod)
- Non-root user (`appuser:appgroup`, uid=1001)
- `HEALTHCHECK` on `/api/v1/health`
- Config validation on startup

---

## Database setup

```bash
# With Docker Compose running PostgreSQL:
export DATABASE_URL=postgresql+asyncpg://tax_user:changeme@localhost:5432/tax_agent

# Run migrations
alembic upgrade head

# Check migration status
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "add_user_table"
```

Models: `User`, `TaxProfile`, `AgentRun` — see `app/db/models/`.

---

## Bedrock setup

Amazon Bedrock requires:
1. AWS CLI configured (`aws configure`) or IAM role (ECS)
2. Bedrock model access enabled in your AWS account

```bash
# Verify AWS identity
aws sts get-caller-identity

# Check Bedrock is accessible
aws bedrock list-foundation-models --region ap-south-1 --query "modelSummaries[].modelId"

# Enable model access in AWS Console:
# AWS Console → Amazon Bedrock → Model access → Request access
# Required: anthropic.claude-3-5-sonnet-20241022-v2:0
```

Set in `.env`:
```
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
AWS_REGION=ap-south-1
```

See [docs/decisions.md](docs/decisions.md#adr-001-amazon-bedrock-as-primary-llm-provider) for why Bedrock was chosen.

---

## Qdrant setup

```bash
# Local (Docker Compose already starts it):
docker compose up qdrant -d
# Available at http://localhost:6333

# Create collection and ingest tax rules:
# (Run after Qdrant is running and DB is migrated)
python -c "
from app.rag.collections import ensure_collection
from app.rag.qdrant_store import get_qdrant_client
from app.rag.embeddings import get_embedding_provider
client = get_qdrant_client()
ensure_collection(client, 'tax_rules', get_embedding_provider().dimension)
print('Collection ready')
"
```

Set in `.env`:
```
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=tax_rules
```

See [docs/rag.md](docs/rag.md) for the full RAG pipeline.

---

## Testing

```bash
# Unit tests (fast, no paid APIs, no live services)
pytest tests/unit/ -v

# Agent + integration tests (mocked LLM, real tools)
pytest tests/agent/ tests/integration/ -v

# All tests
pytest tests/ -q

# Integration tests (requires live Qdrant + DB)
pytest -m integration

# LLM tests (uses real Bedrock — incurs charges!)
pytest -m llm

# Run via script with options
./scripts/run_tests.sh              # unit only
./scripts/run_tests.sh --integration  # + integration
./scripts/run_tests.sh --all          # + LLM (paid)
```

**Test count:** 342 tests as of Milestone 41. All pass with no live services.

---

## Terraform infrastructure

Full guide: [docs/terraform.md](docs/terraform.md)

```bash
cd infra/terraform/environments/dev

# One-time setup
cp dev.tfvars.example dev.tfvars
# Fill in: db_username, db_password

# Standard workflow (always review before apply)
terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="dev.tfvars"

# After reviewing the plan:
terraform apply -var-file="dev.tfvars"

# Get outputs
terraform output ecr_repository_url
terraform output s3_bucket_name
terraform output ecs_cluster_name

# Stop ECS tasks when not in use (zero compute cost)
terraform apply -var-file="dev.tfvars" -var="ecs_desired_count=0"
```

### Cost awareness

| Resource | Dev cost | Notes |
|----------|----------|-------|
| VPC, Subnets, IGW, SG | Free | — |
| S3 | ~$0.023/GB/month | Minimal for dev |
| ECR | ~$0.10/GB/month | ~5 images = very small |
| RDS db.t3.micro | ~$15/month | Stop when not in use |
| ECS Fargate (0 tasks) | $0 | Set `ecs_desired_count=0` |
| ECS Fargate (1 task, 512/1024) | ~$15/month | Only run when testing |
| **NAT Gateway** | **~$35/month** | **NOT created by default** |
| Bedrock | Pay-per-token | See [cost tracking](#cost-control) |

> Always review `terraform plan` output before applying. See [docs/terraform.md](docs/terraform.md) for full cost breakdown.

---

## AWS deployment

Full guide: [docs/deployment.md](docs/deployment.md) · [docs/production_config.md](docs/production_config.md)

```bash
# 1. Push Docker image to ECR
./scripts/deploy_ecr.sh v1.0.0

# 2. Deploy to ECS (with auto-rollback on failure)
./scripts/deploy_ecs.sh v1.0.0 dev

# Or manual Terraform deploy:
cd infra/terraform/environments/dev
terraform apply -var-file="dev.tfvars" \
  -var="image_tag=v1.0.0" \
  -var="ecs_desired_count=1"
```

### GitHub Actions CI/CD

Three workflows (`.github/workflows/`):

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | Push / PR | Unit tests + Terraform validate + Docker build |
| `deploy.yml` | Push to master / manual | Build → ECR push → ECS deploy (OIDC auth) |
| `terraform-plan.yml` | PR with infra changes | Plan and post as PR comment |

**Security:** Deploy uses GitHub OIDC → AWS role assumption. No long-lived `AWS_ACCESS_KEY_ID` in secrets.

---

## Observability

Every agent request emits structured JSON to CloudWatch:

```json
{
  "request_id": "...",
  "user_id": "...",
  "status": "completed",
  "latency_ms": 2340,
  "llm_call_count": 3,
  "tool_call_count": 2,
  "total_input_tokens": 1245,
  "total_output_tokens": 320,
  "estimated_cost_usd": 0.00853,
  "tools_called": ["calculate_tax", "retrieve_tax_rules"],
  "tool_success_rate": 1.0
}
```

Saved CloudWatch Insights queries (created by Terraform):

```
# Agent errors
fields @timestamp, request_id, status, latency_ms
| filter status = "failed" or status = "timeout"
| sort @timestamp desc

# High-cost requests
fields @timestamp, request_id, estimated_cost_usd, iteration_count
| filter estimated_cost_usd > 0.01
| sort estimated_cost_usd desc
```

---

## Evaluation

Full framework: [docs/evaluation.md](docs/evaluation.md)

```bash
# Run evaluation on a labelled dataset
from app.evaluation.runner import EvaluationRunner

runner = EvaluationRunner()

# Retrieval evaluation
report = runner.evaluate_retrieval_batch(examples, k=5)
print(report.to_dict())
# → mean_recall_at_k, mean_precision_at_k, mean_mrr, mean_ndcg_at_k

# Agent evaluation
report = runner.evaluate_agent_batch(agent_states, expected_tools)
print(report.to_dict())
# → task_completion_rate, mean_tool_selection_accuracy, mean_iterations
```

---

## Security

- **Secrets:** Environment variables only. Never in source code, Docker images, or `tfstate`.
- **AWS:** IAM task role for ECS. No long-lived access keys in application.
- **LLM output:** Treated as untrusted input. All tool calls validated via Pydantic before execution.
- **Guardrails:** Prompt injection detection, tool authorization, rate limiting — all before the LLM.
- **S3:** Tax documents are private (public access fully blocked), encrypted at rest (AES256).
- **RDS:** Private subnets only. Accepts connections from ECS tasks only (security group).
- **Container:** Non-root user (`appuser`), multi-stage build (no compiler in production image).
- **CI/CD:** OIDC-based AWS auth. No long-lived credentials in GitHub secrets.

See [docs/decisions.md](docs/decisions.md) for security ADRs.

---

## Cost control

| Control | Value | Where |
|---------|-------|-------|
| `MAX_AGENT_ITERATIONS` | 8 | `.env` |
| `MAX_TOOL_CALLS` | 10 | `.env` |
| `MAX_LLM_CALLS` | 6 | `.env` |
| `DAILY_REQUEST_LIMIT` | 5 | `.env` |
| ECS `desired_count` | 0 (default in dev) | `dev.tfvars` |
| NAT Gateway | Not created by default | `dev.tfvars` → `create_nat_gateway=false` |
| RDS Multi-AZ | Off by default | `dev.tfvars` → `multi_az=false` |

Estimated cost per Bedrock request (Claude Sonnet 4.6):
```
8 LLM calls × ~150 input tokens  = 1,200 input tokens  → $0.0036
8 LLM calls × ~50  output tokens = 400 output tokens   → $0.0060
Total per request: ~$0.01
```

---

## Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Repository + configuration foundation | ✅ |
| 1 | FastAPI + health endpoint | ✅ |
| 2 | PostgreSQL + SQLAlchemy + Alembic | ✅ |
| 3 | LLM abstraction layer | ✅ |
| 4 | Amazon Bedrock integration | ✅ |
| 5 | Structured output (AgentDecision schemas) | ✅ |
| 6 | Tool registry | ✅ |
| 7 | Deterministic tax engine (FY 2024-25) | ✅ |
| 8 | Raw agent loop | ✅ |
| 9 | Agent state | ✅ |
| 10 | Qdrant + embeddings | ✅ |
| 11 | Basic RAG retrieval | ✅ |
| 12 | Hybrid retrieval + RRF | ✅ |
| 13 | Reranking + citations | ✅ |
| 14 | Agentic RAG | ✅ |
| 15 | S3 document upload | ✅ |
| 16 | Document extraction (PDF/OCR/CSV) | ✅ |
| 17 | Tax engine — full deductions + regime comparison | ✅ |
| 18 | Capital gains engine (Budget 2024) | ✅ |
| 19 | Evaluation framework | ✅ |
| 20 | Guardrails | ✅ |
| 21 | Observability + request tracing | ✅ |
| 22 | Rate limiting + cost tracking | ✅ |
| 23 | LangChain evaluation (comparison docs) | ✅ |
| 24 | LangChain implementation | ✅ |
| 25 | LangGraph evaluation (comparison docs) | ✅ |
| 26 | LangGraph implementation | ✅ |
| 27 | Production Docker image (multi-stage) | ✅ |
| 28 | Terraform networking (VPC, subnets, SGs) | ✅ |
| 29 | Terraform S3 + IAM | ✅ |
| 30 | Terraform ECR | ✅ |
| 31 | Terraform RDS PostgreSQL | ✅ |
| 32 | Terraform ECS/Fargate | ✅ |
| 33 | Terraform CloudWatch | ✅ |
| 34 | Secrets Manager integration | ✅ |
| 35 | Bedrock IAM validation | ✅ |
| 36 | ECR deploy scripts | ✅ |
| 37 | ECS deploy + agent API endpoint | ✅ |
| 38 | Production configuration | ✅ |
| 39 | End-to-end testing | ✅ |
| 40 | CI/CD (GitHub Actions) | ✅ |
| 41 | Production hardening | ✅ |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/architecture.md](docs/architecture.md) | Full system design, request lifecycle, layer separation, technology decisions |
| [docs/agent.md](docs/agent.md) | Raw agent loop walkthrough, state machine, tool registry, safety limits |
| [docs/rag.md](docs/rag.md) | RAG pipeline stages, hybrid retrieval, agentic RAG, evaluation metrics |
| [docs/langchain_comparison.md](docs/langchain_comparison.md) | Raw vs LangChain — full comparison table, what to replace, what to keep |
| [docs/langgraph_comparison.md](docs/langgraph_comparison.md) | LangGraph — when to use, state graph, human-in-the-loop, multi-agent |
| [docs/terraform.md](docs/terraform.md) | Infrastructure guide, commands, remote state, cost awareness |
| [docs/deployment.md](docs/deployment.md) | ECR push, ECS deploy, rollback, DB migrations |
| [docs/production_config.md](docs/production_config.md) | Production checklist, secrets injection, CORS, monitoring |
| [docs/evaluation.md](docs/evaluation.md) | All metrics with formulas, examples, and interpretation |
| [docs/decisions.md](docs/decisions.md) | ADRs — why Bedrock, Qdrant, PostgreSQL, ECS, Terraform, raw loop |

---

## Troubleshooting

### Config check fails: `BEDROCK_MODEL_ID is required`
```
Set LLM_PROVIDER=bedrock and BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0 in .env
```

### `NoCredentialsError` when calling Bedrock
```bash
aws configure          # set up AWS CLI profile
aws sts get-caller-identity  # verify it works
```

### Qdrant connection refused
```bash
docker compose up qdrant -d
curl http://localhost:6333/health
```

### `DATABASE_URL` not set
```bash
# Add to .env:
DATABASE_URL=postgresql+asyncpg://tax_user:changeme@localhost:5432/tax_agent

# Make sure PostgreSQL is running:
docker compose up postgres -d
```

### Alembic migration fails
```bash
alembic current          # check current state
alembic history          # see migration history
alembic upgrade head     # apply all pending migrations
```

### ECS task keeps restarting
```bash
# Check CloudWatch logs
aws logs tail /ecs/ai-tax-agent-dev --follow --region ap-south-1

# Common causes:
# - Missing environment variables (check ECS task definition)
# - DB connection failure (check security group + subnet)
# - Image missing (push to ECR first)
```

### Terraform plan shows unexpected changes
```bash
terraform refresh -var-file=dev.tfvars   # sync state with reality
terraform plan -var-file=dev.tfvars      # re-review plan
```

### High token costs
```bash
# Reduce limits in .env:
MAX_AGENT_ITERATIONS=4
MAX_LLM_CALLS=3
DAILY_REQUEST_LIMIT=3

# Check cost breakdown in CloudWatch:
# Filter: estimated_cost_usd > 0.005
```
