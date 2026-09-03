# AWS Cost Estimate

> Target: ₹3,000–₹5,500/month under low traffic

---

## Cost breakdown (ap-south-1, as of 2024)

| Resource | Type | Est. Cost/month |
|----------|------|----------------|
| **EC2 Spot** | t4g.small (2 vCPU, 2GB) | ~₹700–₹1,200 |
| **EBS** | 20GB gp3 | ~₹150 |
| **RDS** | db.t4g.micro, 20GB | ~₹1,200 |
| **Public IPv4** | 1 address | ~₹300 |
| **S3** | 10GB storage + requests | ~₹100 |
| **ECR** | 2 repos, ~2GB total | ~₹20 |
| **CloudWatch** | Logs + basic metrics | ~₹100 |
| **Bedrock** | ~500 requests × $0.01 | ~₹415 |
| **Data transfer** | Minimal | ~₹50–₹200 |
| **Total** | | **~₹3,000–₹3,700** |

> ⚠️ Qdrant uses free tier initially (1GB, 1 node) — $0

---

## What we intentionally avoided

| Resource | Cost saved | Reason |
|----------|-----------|--------|
| ALB (Application Load Balancer) | ~₹1,500/month | Not needed for single EC2 |
| NAT Gateway | ~₹2,900/month | Avoided by using public subnet |
| ECS/Fargate | ~₹1,500+/month | EC2 Spot is cheaper at low scale |
| EKS | ~₹5,000+/month | Massive overkill |
| OpenSearch | ~₹3,000+/month | Using Qdrant Cloud free tier |
| Multi-AZ RDS | 2× RDS cost | Single AZ acceptable for dev/early prod |

---

## Cost controls

1. **EC2 Spot interruption** — Application is stateless; restart is automatic
2. **EC2 stop when idle** — Stop the instance when not in use (EBS persists)
3. **RDS stop** — Stop RDS manually during off-hours (resumes in < 1 min)
4. **Bedrock limits** — `MAX_AGENT_ITERATIONS=8`, `DAILY_REQUEST_LIMIT=20`
5. **Qdrant free tier** — 1GB / 1 collection / unlimited vectors up to limit

---

## Scaling costs

| Scale | Architecture | Est. Cost/month |
|-------|-------------|-----------------|
| **Now** (< 100 users) | EC2 Spot + Qdrant free | ₹3,000–₹4,000 |
| **Growing** (< 1K users) | EC2 + paid Qdrant | ₹5,000–₹8,000 |
| **Scaling** (< 10K users) | ECS Fargate + ALB | ₹15,000–₹25,000 |

---

## AWS Free Tier (first 12 months)

- EC2 t2.micro: 750 hours/month (Spot is NOT covered)
- RDS db.t3.micro: 750 hours/month (may reduce RDS cost)
- S3: 5GB free
- CloudWatch: 10 metrics, 1M API calls

> Always verify current pricing at https://aws.amazon.com/pricing/
