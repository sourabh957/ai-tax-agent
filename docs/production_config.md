# Production Configuration Guide

## Environment variables

All configuration is via environment variables. In production (ECS), these are
injected via the ECS task definition — either as plain env vars or via
Secrets Manager secret injection.

### Non-secret (ECS task definition `environment` block)

```
APP_ENV=production
LOG_LEVEL=INFO
AWS_REGION=ap-south-1
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
S3_BUCKET_NAME=ai-tax-agent-prod-documents-<suffix>
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_COLLECTION=tax_rules
MAX_AGENT_ITERATIONS=8
MAX_TOOL_CALLS=10
MAX_LLM_CALLS=6
DAILY_REQUEST_LIMIT=20
```

### Secrets (ECS task definition `secrets` block — from Secrets Manager)

| Env var | Secrets Manager path | Description |
|---------|---------------------|-------------|
| `DATABASE_URL` | `ai-tax-agent-prod/db-credentials` | Full PostgreSQL connection string |
| `QDRANT_API_KEY` | `ai-tax-agent-prod/qdrant-api-key` | Qdrant cloud API key |

**Never inject these as plain text environment variables.**

---

## Production hardening checklist

### Application
- [ ] `APP_ENV=production` — disables Swagger UI (`/docs`) and ReDoc (`/redoc`)
- [ ] `LOG_LEVEL=INFO` — no DEBUG logs in production (may expose internal state)
- [ ] All secrets via Secrets Manager — never in ECS `environment` block
- [ ] CORS configured to specific origins (not `*`)
- [ ] Rate limiting enabled and tuned (`DAILY_REQUEST_LIMIT`)

### AWS
- [ ] ECS task role — least privilege (see `infra/terraform/modules/iam/`)
- [ ] RDS not publicly accessible — private subnets only
- [ ] S3 bucket — public access fully blocked, AES256 encryption
- [ ] ECR image scanning enabled (configured in Terraform)
- [ ] CloudWatch log retention set (14 days dev, 90 days prod)
- [ ] CloudWatch alarms configured for CPU, memory

### Secrets
- [ ] No secrets in `.env` files committed to Git
- [ ] No secrets in Terraform tfstate (DB credentials set post-apply via AWS CLI)
- [ ] No secrets in Docker image (verified via `.dockerignore`)
- [ ] IAM task role — no long-lived access keys, no AWS credentials in image

### Networking
- [ ] ECS tasks in private subnets (enable NAT Gateway for production)
- [ ] RDS security group — accepts connections from ECS tasks only
- [ ] API accessible via ALB (not directly via task public IP in production)

---

## CORS configuration

Development (`APP_ENV=development`):
```python
allow_origins=["*"]
```

Production — tighten to specific origins in `app/main.py`:
```python
allow_origins=["https://yourdomain.com", "https://app.yourdomain.com"]
```

---

## Swagger / ReDoc

Development: available at `/docs` and `/redoc`

Production (`APP_ENV=production`): both disabled automatically.

---

## Database migrations in production

Run Alembic migrations before starting the new ECS task:

```bash
# Using ECS Exec (requires `enableExecuteCommand=true` on service)
aws ecs execute-command \
  --cluster ai-tax-agent-prod-cluster \
  --task <task-id> \
  --container ai-tax-agent-api \
  --interactive \
  --command "alembic upgrade head"

# Or via a one-off ECS task (recommended for production)
aws ecs run-task \
  --cluster ai-tax-agent-prod-cluster \
  --task-definition ai-tax-agent-prod-task \
  --overrides '{"containerOverrides":[{"name":"ai-tax-agent-api","command":["alembic","upgrade","head"]}]}'
```

---

## Rollback procedure

```bash
# 1. Identify the previous task definition revision
aws ecs describe-services \
  --cluster ai-tax-agent-prod-cluster \
  --services ai-tax-agent-prod-service \
  --query "services[0].deployments"

# 2. Update service to previous revision
aws ecs update-service \
  --cluster ai-tax-agent-prod-cluster \
  --service ai-tax-agent-prod-service \
  --task-definition ai-tax-agent-prod-task:<previous-revision> \
  --force-new-deployment

# 3. Wait for stability
aws ecs wait services-stable \
  --cluster ai-tax-agent-prod-cluster \
  --services ai-tax-agent-prod-service
```

---

## Cost controls

| Control | Setting | Notes |
|---------|---------|-------|
| `MAX_AGENT_ITERATIONS` | 8 | Hard stop on LLM calls per request |
| `MAX_TOOL_CALLS` | 10 | Hard stop on tool calls per request |
| `MAX_LLM_CALLS` | 6 | Hard stop on LLM API calls per request |
| `DAILY_REQUEST_LIMIT` | 20 | Per-user daily cap |
| ECS desired_count | 0 | Set to 0 when not in use (no Fargate charges) |
| RDS | Stop DB | Stop RDS instance when not in use (dev only) |

---

## Monitoring

CloudWatch Logs Insights queries (saved in Terraform):

```
# Agent errors
fields @timestamp, request_id, user_id, status, latency_ms
| filter status = "failed" or status = "timeout"
| sort @timestamp desc

# High cost requests
fields @timestamp, request_id, estimated_cost_usd, iteration_count
| filter estimated_cost_usd > 0.01
| sort estimated_cost_usd desc
```
